import type { AgentRunStatus } from "@/types/agents";

const LABELS: Record<AgentRunStatus, string> = {
  planning: "Planning",
  running: "Working",
  awaiting_approval: "Approval required",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  timed_out: "Timed out",
};

const TONES: Record<AgentRunStatus, string> = {
  planning: "bg-violet-500/15 text-violet-100 ring-violet-400/30",
  running: "bg-cyan-500/15 text-cyan-100 ring-cyan-400/30",
  awaiting_approval: "bg-amber-500/15 text-amber-100 ring-amber-400/30",
  completed: "bg-emerald-500/15 text-emerald-100 ring-emerald-400/30",
  failed: "bg-rose-500/15 text-rose-100 ring-rose-400/30",
  cancelled: "bg-slate-500/20 text-slate-200 ring-slate-400/30",
  timed_out: "bg-orange-500/15 text-orange-100 ring-orange-400/30",
};

export function AgentRunStatusBadge({ status }: { status: AgentRunStatus }) {
  return (
    <span className={`inline-flex rounded-md px-2 py-1 text-xs font-medium ring-1 ${TONES[status]}`}>
      {LABELS[status]}
    </span>
  );
}
