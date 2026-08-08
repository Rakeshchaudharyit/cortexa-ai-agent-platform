import { AgentIdentityBadge } from "@/components/agents/AgentIdentityBadge";
import type { AgentTask } from "@/types/agents";

const TASK_LABELS: Record<AgentTask["status"], string> = {
  pending: "Waiting",
  ready: "Ready",
  running: "Working",
  awaiting_approval: "Approval required",
  succeeded: "Completed",
  skipped: "Skipped",
  failed: "Failed",
  cancelled: "Cancelled",
  timed_out: "Timed out",
};

export function AgentTaskCard({ task }: { task: AgentTask }) {
  return (
    <li className="rounded-xl border border-white/10 bg-slate-950/40 p-3" data-testid={`agent-task-${task.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white/5 text-xs text-slate-400">
            {task.sequence}
          </span>
          <AgentIdentityBadge agentKey={task.assigned_agent_key} />
        </div>
        <span className="text-xs font-medium text-slate-300">{TASK_LABELS[task.status]}</span>
      </div>
      <p className="mt-2 text-sm font-medium text-slate-100">{task.objective}</p>
      {task.result_summary ? <p className="mt-1 text-xs text-slate-400">{task.result_summary}</p> : null}
      {task.safe_error_message ? <p className="mt-1 text-xs text-rose-200">{task.safe_error_message}</p> : null}
      <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-500">
        {task.duration_ms != null ? <span>{task.duration_ms} ms</span> : null}
        {task.retry_count ? <span>{task.retry_count} {task.retry_count === 1 ? "retry" : "retries"}</span> : null}
        {task.requires_approval ? <span>Approval gated</span> : null}
      </div>
    </li>
  );
}
