import { AgentRunStatusBadge } from "@/components/agents/AgentRunStatusBadge";
import type { AgentRunSummary as Run } from "@/types/agents";

function duration(value: number | null) {
  if (value == null) return "In progress";
  return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${value} ms`;
}

export function AgentRunSummary({ run }: { run: Run }) {
  return (
    <section className="rounded-2xl border border-cyan-400/15 bg-slate-900/60 p-5" data-testid="agent-run-summary">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-300">Coordinated execution</p>
          <h2 className="mt-2 text-lg font-semibold text-white">{run.original_request_summary}</h2>
        </div>
        <AgentRunStatusBadge status={run.status} />
      </div>
      <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[["Tasks", run.task_count], ["Tool calls", run.tool_calls_used], ["LLM calls", run.llm_calls_used], ["Duration", duration(run.duration_ms)]].map(([label, value]) => (
          <div key={String(label)} className="rounded-xl bg-black/20 p-3">
            <dt className="text-[11px] uppercase tracking-wide text-slate-500">{label}</dt>
            <dd className="mt-1 text-sm font-semibold text-slate-100">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
