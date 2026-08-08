import { AgentIdentityBadge, agentIdentity } from "@/components/agents/AgentIdentityBadge";
import type { AgentRunEvent } from "@/types/agents";

const IMPORTANT = new Set([
  "run_started", "planning_started", "plan_created", "task_started", "task_completed",
  "task_failed", "task_retrying", "task_skipped", "handoff", "approval_required", "approval_resolved",
  "run_completed", "run_failed", "run_cancelled", "run_timed_out",
]);

function eventLabel(event: AgentRunEvent): string {
  if (event.event_type === "handoff") {
    const from = typeof event.safe_metadata?.from === "string" ? event.safe_metadata.from : event.agent_key;
    const to = typeof event.safe_metadata?.to === "string" ? event.safe_metadata.to : null;
    return `${agentIdentity(from).label} handed work to ${agentIdentity(to).label}`;
  }
  const labels: Record<string, string> = {
    run_started: "Coordinated response started",
    planning_started: "Planning the work",
    plan_created: "Execution plan ready",
    task_started: "Task started",
    task_completed: "Task completed",
    task_failed: "Task failed",
    task_retrying: "Temporary failure detected · retrying task",
    task_skipped: "Task skipped",
    approval_required: "User approval requested",
    approval_resolved: "Approval resolved",
    run_completed: "Coordinated response completed",
    run_failed: "Coordinated response failed",
    run_cancelled: "Coordinated response cancelled",
    run_timed_out: "Coordinated response timed out",
  };
  return labels[event.event_type] ?? event.event_type.replaceAll("_", " ");
}

export function AgentTimeline({ events }: { events: AgentRunEvent[] }) {
  const visible = events.filter((event) => IMPORTANT.has(event.event_type));
  return (
    <ol className="space-y-3" data-testid="agent-timeline">
      {visible.map((event) => (
        <li key={event.id} className="relative border-l border-cyan-400/20 pl-4">
          <span className="absolute -left-1 top-1.5 h-2 w-2 rounded-full bg-cyan-300" aria-hidden="true" />
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm text-slate-200">{eventLabel(event)}</p>
            {event.agent_key ? <AgentIdentityBadge agentKey={event.agent_key} /> : null}
          </div>
          <time className="text-[11px] text-slate-500">{new Date(event.created_at).toLocaleString()}</time>
        </li>
      ))}
    </ol>
  );
}
