/**
 * Phase 6 agent tools UI tests.
 */
import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";

import { ToolActivity, ToolExecutionCard } from "@/components/chat/ToolExecutionCard";
import { MessageList } from "@/components/chat/MessageList";
import type { ConversationMessage, ToolActivityItem, ToolExecutionSummary } from "@/types/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

afterEach(() => {
  cleanup();
});

function sampleMessage(overrides: Partial<ConversationMessage> = {}): ConversationMessage {
  return {
    id: "msg-1",
    conversation_id: "conv-1",
    role: "assistant",
    content: "Final answer",
    status: "complete",
    sequence_number: 2,
    is_active: true,
    grounded: null,
    model: "fake-model",
    provider: "fake",
    prompt_tokens: null,
    completion_tokens: null,
    total_tokens: null,
    latency_ms: null,
    finish_reason: "stop",
    error_code: null,
    regenerated_from_message_id: null,
    edited_from_message_id: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    citations: [],
    tool_executions: [],
    ...overrides,
  };
}

describe("ToolExecutionCard", () => {
  it("shows calculator activity while started", () => {
    render(
      <ToolExecutionCard
        activity={{ id: "1", tool_name: "calculator", status: "started" }}
      />,
    );
    expect(screen.getByText("Using calculator…")).toBeInTheDocument();
    expect(screen.getByTestId("tool-execution-card")).toHaveAttribute("aria-busy", "true");
  });

  it("shows success completion", () => {
    render(
      <ToolExecutionCard
        activity={{
          id: "1",
          tool_name: "calculator",
          status: "succeeded",
          result: { expression: "(2450 * 18) / 100", result: 441 },
        }}
      />,
    );
    expect(screen.getByText(/calculator completed/i)).toBeInTheDocument();
  });

  it("shows safe failure without stack traces", () => {
    render(
      <ToolExecutionCard
        activity={{
          id: "1",
          tool_name: "calculator",
          status: "failed",
          error_message: "Division by zero",
        }}
      />,
    );
    expect(screen.getByTestId("tool-error-message")).toHaveTextContent("Division by zero");
    expect(screen.queryByText(/Traceback/i)).not.toBeInTheDocument();
  });

  it("expands calculator structured result", () => {
    render(
      <ToolExecutionCard
        activity={{
          id: "1",
          tool_name: "calculator",
          status: "succeeded",
          result: { expression: "(1200 * 15) / 100", result: 180 },
        }}
      />,
    );
    fireEvent.click(screen.getByTestId("tool-result-toggle"));
    expect(screen.getByTestId("tool-result-details").textContent).toContain("180");
  });
});

describe("ToolActivity ordering", () => {
  it("renders multiple tool events in order", () => {
    const items: ToolActivityItem[] = [
      { id: "a", tool_name: "calculator", status: "succeeded" },
      { id: "b", tool_name: "current_datetime", status: "succeeded" },
    ];
    const { container } = render(<ToolActivity items={items} />);
    const root = within(container);
    const cards = root.getAllByTestId("tool-execution-card");
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveAttribute("data-tool-name", "calculator");
    expect(cards[1]).toHaveAttribute("data-tool-name", "current_datetime");
  });
});

describe("MessageList tool streaming", () => {
  it("shows tool-start activity and final assistant text", () => {
    const { container } = render(
      <MessageList
        messages={[]}
        streaming={{
          content: "The result is 441.",
          citations: [],
          userMessageId: "u1",
          assistantMessageId: "a1",
          toolActivity: [
            { id: "c1", tool_name: "calculator", status: "succeeded", result: { result: 441 } },
          ],
        }}
      />,
    );
    expect(within(container).getByTestId("tool-activity")).toBeInTheDocument();
    expect(within(container).getByText(/The result is 441/)).toBeInTheDocument();
  });

  it("shows knowledge search activity and keeps citations visible on completed messages", () => {
    const msg = sampleMessage({
      content: "Based on your docs [1]",
      citations: [
        {
          id: "cit-1",
          citation_index: 1,
          citation_id: "[1]",
          document_id: "d1",
          chunk_id: "c1",
          filename: "notes.txt",
          page_number: 1,
          chunk_index: 0,
          excerpt: "Cortexa is local-first",
          similarity_score: 0.9,
        },
      ],
      tool_executions: [
        {
          id: "te1",
          tool_name: "knowledge_search",
          tool_version: "1.0.0",
          status: "succeeded",
          conversation_id: "conv-1",
          message_id: "msg-1",
          arguments_summary: { query: "Cortexa" },
          result_summary: { count: 1 },
          error_code: null,
          error_message: null,
          started_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
          duration_ms: 12,
          created_at: new Date().toISOString(),
        } satisfies ToolExecutionSummary,
      ],
    });
    const { container } = render(<MessageList messages={[msg]} streaming={null} />);
    expect(within(container).getAllByTestId("tool-activity").length).toBeGreaterThan(0);
    expect(within(container).getByTestId("citations-list")).toBeInTheDocument();
  });

  it("keeps existing empty chat behavior", () => {
    render(<MessageList messages={[]} streaming={null} />);
    expect(screen.getByTestId("messages-empty")).toBeInTheDocument();
  });
});

describe("tools page helpers", () => {
  it("loads via listToolExecutions mock shape", async () => {
    const { listToolExecutions } = await import("@/services/tools");
    expect(typeof listToolExecutions).toBe("function");
  });
});
