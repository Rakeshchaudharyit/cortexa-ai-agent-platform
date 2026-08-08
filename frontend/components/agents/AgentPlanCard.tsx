"use client";

import { useState } from "react";
import { AgentTaskCard } from "@/components/agents/AgentTaskCard";
import type { AgentTask } from "@/types/agents";

export function AgentPlanCard({ summary, tasks }: { summary: string | null; tasks: AgentTask[] }) {
  const [expanded, setExpanded] = useState(true);
  const ordered = [...tasks].sort((a, b) => a.sequence - b.sequence);
  return (
    <section className="overflow-hidden rounded-2xl border border-violet-400/20 bg-violet-500/[0.06]" data-testid="agent-plan-card">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        aria-label={`${expanded ? "Collapse" : "Expand"} coordinated execution plan`}
        className="flex min-h-11 w-full items-center justify-between gap-3 px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300"
      >
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-violet-200">
            {tasks.length ? `Plan ready · ${tasks.length} tasks` : "Planning in progress"}
          </p>
          <p className="mt-1 text-sm text-slate-300">{summary || "Bounded multi-agent execution plan"}</p>
        </div>
        <span aria-hidden="true" className="text-violet-200">{expanded ? "−" : "+"}</span>
      </button>
      {expanded && ordered.length ? (
        <ol className="space-y-2 border-t border-violet-400/10 p-3">
          {ordered.map((task) => (
            <AgentTaskCard key={task.id} task={task} />
          ))}
        </ol>
      ) : null}
    </section>
  );
}
