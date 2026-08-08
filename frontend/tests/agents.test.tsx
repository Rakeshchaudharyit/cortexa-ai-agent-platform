import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentApprovalCard } from "@/components/agents/AgentApprovalCard";
import { AgentPlanCard } from "@/components/agents/AgentPlanCard";
import { AgentTimeline } from "@/components/agents/AgentTimeline";
import { AgentRunActivity } from "@/components/agents/AgentRunActivity";
import { RunEmptyState } from "@/components/agents/RunEmptyState";
import type { AgentApproval, AgentRunEvent, AgentTask } from "@/types/agents";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ runId: "r1", agentKey: "knowledge" }),
}));


vi.mock("@/services/conversations", () => ({
  createConversation: vi.fn(),
  streamMessage: vi.fn(),
}));

vi.mock("@/services/agents", () => ({
  approveAgentApproval: vi.fn(),
  rejectAgentApproval: vi.fn(),
  listAgentRuns: vi.fn(),
  listAdminAgentRuns: vi.fn(),
  getAgentRun: vi.fn(),
  listAdminAgents: vi.fn(),
  updateAdminAgent: vi.fn(),
}));

import AgentRunsPage from "@/app/agent-runs/page";
import AdminAgentRunsPage from "@/app/admin/agent-runs/page";
import AdminAgentsPage from "@/app/admin/agents/page";
import { createConversation, streamMessage } from "@/services/conversations";
import {
  approveAgentApproval,
  getAgentRun,
  listAdminAgentRuns,
  listAdminAgents,
  listAgentRuns,
  rejectAgentApproval,
} from "@/services/agents";

afterEach(cleanup);

const tasks: AgentTask[] = [
  { id: "t2", assigned_agent_key: "tool", task_type: "calculate", objective: "Tool agent task", status: "running", sequence: 2, depth: 0, requires_approval: false, result_summary: null, error_code: null, safe_error_message: null, retry_count: 1, duration_ms: null },
  { id: "t1", assigned_agent_key: "knowledge", task_type: "retrieve", objective: "Knowledge agent task", status: "succeeded", sequence: 1, depth: 0, requires_approval: false, result_summary: "Task succeeded", error_code: null, safe_error_message: null, retry_count: 0, duration_ms: 120 },
  { id: "t3", assigned_agent_key: "conversation", task_type: "respond", objective: "Conversation agent task", status: "skipped", sequence: 3, depth: 0, requires_approval: false, result_summary: "Task skipped", error_code: null, safe_error_message: null, retry_count: 0, duration_ms: 0 },
];

const approval: AgentApproval = { id: "a1", agent_run_id: "r1", task_id: "t2", action_type: "memory_remember", status: "pending", safe_action_summary: "Confirm memory remember action", requested_at: "2026-08-01T10:00:00Z", expires_at: "2026-08-02T10:00:00Z", resolved_at: null, resolution_note: null };

describe("multi-agent activity components", () => {
  beforeEach(() => vi.clearAllMocks());

  it("keeps the launcher stream open until the final response is persisted", async () => {
    const user = userEvent.setup();
    const observed: string[] = [];
    vi.mocked(listAgentRuns).mockResolvedValue({
      ok: true,
      status: 200,
      data: { items: [], total: 0, limit: 12, offset: 0 },
    });
    vi.mocked(createConversation).mockResolvedValue({
      ok: true,
      status: 201,
      data: {
        id: "conversation-1",
        title: "Agent execution",
        status: "active",
        created_at: "2026-08-04T10:00:00Z",
        updated_at: "2026-08-04T10:00:00Z",
        last_message_at: null,
        message_count: 0,
        archived_at: null,
        title_is_auto: false,
        summary_preview: null,
      },
    });
    vi.mocked(streamMessage).mockImplementation(async function* () {
      observed.push("run_started");
      yield { event: "run_started", data: { agent_run_id: "run-1" } };
      observed.push("run_completed");
      yield { event: "run_completed", data: { agent_run_id: "run-1" } };
      observed.push("complete");
      yield {
        event: "complete",
        data: { agent_run_id: "run-1", message: { id: "assistant-1", content: "Saved answer" } },
      };
    });

    render(<AgentRunsPage />);
    await user.click(await screen.findByRole("button", { name: /new agent run/i }));
    await user.type(
      screen.getByLabelText(/objective/i),
      "Review available knowledge and produce a production recommendation.",
    );
    await user.click(screen.getByRole("button", { name: /run with ai agents/i }));

    await waitFor(() => expect(observed).toEqual(["run_started", "run_completed", "complete"]));
    expect(pushMock).toHaveBeenCalledTimes(1);
    expect(pushMock).toHaveBeenCalledWith("/agent-runs/run-1");
  });

  it("opens the new agent run launcher from execution history", async () => {
    const user = userEvent.setup();
    vi.mocked(listAgentRuns).mockResolvedValue({
      ok: true,
      status: 200,
      data: { items: [], total: 0, limit: 12, offset: 0 },
    });

    render(<AgentRunsPage />);
    await user.click(await screen.findByRole("button", { name: /new agent run/i }));

    expect(screen.getByRole("dialog", { name: /new agent run/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run with ai agents/i })).toBeDisabled();
    expect(screen.getByLabelText(/objective/i)).toBeInTheDocument();
  });

  it("renders a safe ordered plan and supports keyboard-compatible expansion", async () => {
    const user = userEvent.setup();
    render(<AgentPlanCard summary="Multi-agent execution plan" tasks={tasks} />);
    expect(screen.getByText("Plan ready · 3 tasks")).toBeInTheDocument();
    const cards = screen.getAllByTestId(/agent-task-/);
    expect(cards[0]).toHaveTextContent("Knowledge agent task");
    expect(cards[1]).toHaveTextContent("Tool agent task");
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("Skipped")).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /collapse coordinated/i });
    await user.click(toggle);
    expect(screen.queryByText("Knowledge agent task")).not.toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("approves exactly once while the approval request is pending", async () => {
    const user = userEvent.setup();
    let resolveRequest = (value: { ok: true; status: number; data: AgentApproval }) => {
      void value;
    };
    vi.mocked(approveAgentApproval).mockReturnValue(new Promise((resolve) => { resolveRequest = resolve; }));
    render(<AgentApprovalCard approval={approval} />);
    const button = screen.getByRole("button", { name: "Approve and continue" });
    await user.click(button);
    await user.click(button);
    expect(approveAgentApproval).toHaveBeenCalledTimes(1);
    resolveRequest({ ok: true, status: 200, data: { ...approval, status: "approved" } });
    await waitFor(() => expect(screen.getByText(/Approved · Resuming/)).toBeInTheDocument());
  });

  it("rejects once and renders the persisted resolution", async () => {
    const user = userEvent.setup();
    vi.mocked(rejectAgentApproval).mockResolvedValue({ ok: true, status: 200, data: { ...approval, status: "rejected" } });
    render(<AgentApprovalCard approval={approval} />);
    await user.click(screen.getByRole("button", { name: "Reject approval" }));
    expect(rejectAgentApproval).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByText("rejected")).toBeInTheDocument());
  });

  it("renders bounded retry events in the live timeline", () => {
    const events: AgentRunEvent[] = [
      {
        id: "retry-1",
        event_type: "task_retrying",
        agent_key: "knowledge",
        task_id: "t1",
        safe_metadata: { failure_category: "transient", attempt: 1 },
        created_at: "2026-08-01T10:00:00Z",
      },
    ];
    render(<AgentTimeline events={events} />);
    expect(screen.getByText("Temporary failure detected · retrying task")).toBeInTheDocument();
  });

  it("renders meaningful handoffs and terminal events without private payloads", () => {
    const events: AgentRunEvent[] = [
      { id: "e1", event_type: "handoff", agent_key: "knowledge", task_id: "t1", safe_metadata: { from: "knowledge", to: "tool" }, created_at: "2026-08-01T10:00:00Z" },
      { id: "e2", event_type: "run_completed", agent_key: "coordinator", task_id: null, safe_metadata: null, created_at: "2026-08-01T10:01:00Z" },
    ];
    render(<AgentTimeline events={events} />);
    expect(screen.getByText("Knowledge Agent handed work to Tool Agent")).toBeInTheDocument();
    expect(screen.getByText("Coordinated response completed")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/prompt|secret|document passage/i);
  });

  it("explains why simple chats do not appear in empty run history", () => {
    render(<RunEmptyState />);
    expect(screen.getByText("No coordinated agent runs yet.")).toBeInTheDocument();
    expect(screen.getByText(/simple chats use the fast response path/i)).toBeInTheDocument();
  });

  it("reconstructs a pending approval from persisted run state without duplicate cards", async () => {
    vi.mocked(getAgentRun).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        id: "r1", status: "awaiting_approval", execution_mode: "multi_agent",
        original_request_summary: "[private user request]", safe_plan_summary: "Multi-agent execution plan",
        started_at: "2026-08-01T10:00:00Z", completed_at: null, duration_ms: null,
        steps_used: 1, llm_calls_used: 1, tool_calls_used: 0, task_count: tasks.length,
        correlation_id: "c1", error_code: null, safe_error_message: null,
        created_at: "2026-08-01T10:00:00Z", conversation_id: "conversation-1",
        tasks, approvals: [approval], events: [],
      },
    });
    const { rerender } = render(<AgentRunActivity runId="r1" revision={1} />);
    expect(await screen.findByTestId("agent-approval-a1")).toBeInTheDocument();
    rerender(<AgentRunActivity runId="r1" revision={2} />);
    await waitFor(() => expect(getAgentRun).toHaveBeenCalledTimes(2));
    expect(screen.getAllByTestId("agent-approval-a1")).toHaveLength(1);
  });
});

describe("agent run history pages", () => {
  const run = {
    id: "r1",
    status: "completed" as const,
    execution_mode: "multi_agent" as const,
    original_request_summary: "[private user request]",
    safe_plan_summary: "Multi-agent execution plan",
    started_at: "2026-08-01T10:00:00Z",
    completed_at: "2026-08-01T10:00:01Z",
    duration_ms: 1000,
    steps_used: 3,
    llm_calls_used: 2,
    tool_calls_used: 1,
    task_count: 3,
    correlation_id: "correlation-1",
    error_code: null,
    safe_error_message: null,
    created_at: "2026-08-01T10:00:00Z",
  };

  beforeEach(() => vi.clearAllMocks());

  it("renders owned runs, filters, pagination state, and safe links", async () => {
    vi.mocked(listAgentRuns).mockResolvedValue({
      ok: true,
      status: 200,
      data: { items: [run], total: 1, limit: 12, offset: 0 },
    });
    render(<AgentRunsPage />);
    expect((await screen.findAllByText("[private user request]")).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /view run/i })).toHaveAttribute("href", "/agent-runs/r1");
    await userEvent.selectOptions(screen.getByLabelText("Status"), "completed");
    await waitFor(() => expect(listAgentRuns).toHaveBeenLastCalledWith(expect.objectContaining({ status: "completed" })));
    expect(screen.getByText("1–1 of 1")).toBeInTheDocument();
  });

  it("renders redacted admin run metadata and navigates to safe detail", async () => {
    vi.mocked(listAdminAgentRuns).mockResolvedValue({
      ok: true,
      status: 200,
      data: { items: [{ ...run, user_id: "user-1", conversation_id: "conversation-1" }], total: 1, limit: 25, offset: 0 },
    });
    render(<AdminAgentRunsPage />);
    expect((await screen.findAllByText("[private user request]")).length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(/raw prompt|secret value|document passage/i);
    await userEvent.click(screen.getAllByText("[private user request]")[0]!);
    expect(pushMock).toHaveBeenCalledWith("/admin/agent-runs/r1");
  });

  it("marks required agents immutable and confirms optional disable", async () => {
    const definitions = [
      { key: "coordinator", display_name: "Coordinator", description: "Coordinates bounded plans", version: "1", enabled: true, system_managed: true, capabilities: ["coordination"], allowed_tools: [], maximum_steps: 8, timeout_seconds: 60, required_for_multi_agent: true },
      { key: "knowledge", display_name: "Knowledge Agent", description: "Retrieves safe context", version: "1", enabled: true, system_managed: true, capabilities: ["retrieval"], allowed_tools: ["knowledge_search"], maximum_steps: 4, timeout_seconds: 30, required_for_multi_agent: false },
    ];
    vi.mocked(listAdminAgents).mockResolvedValue({
      ok: true,
      status: 200,
      data: { items: definitions, total: 2 },
    });
    render(<AdminAgentsPage />);
    expect((await screen.findAllByText("Coordinator")).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Disable Coordinator" })[0]).toBeDisabled();
    await userEvent.click(
      screen.getAllByRole("button", { name: "Disable Knowledge Agent" })[0]!,
    );
    expect(screen.getByTestId("admin-confirm-dialog")).toHaveTextContent(
      "Disable optional agent",
    );
  });
  it("shows planning in progress instead of a ready zero-task plan", () => {
    render(<AgentPlanCard summary="Preparing the execution plan" tasks={[]} />);
    expect(screen.getByText("Planning in progress")).toBeInTheDocument();
    expect(screen.queryByText(/Plan ready · 0 tasks/)).not.toBeInTheDocument();
  });

});
