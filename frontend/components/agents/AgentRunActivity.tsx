"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AgentApprovalCard } from "@/components/agents/AgentApprovalCard";
import { AgentPlanCard } from "@/components/agents/AgentPlanCard";
import { AgentRunStatusBadge } from "@/components/agents/AgentRunStatusBadge";
import { AgentTimeline } from "@/components/agents/AgentTimeline";
import { getAgentRun } from "@/services/agents";
import type { AgentRunDetail } from "@/types/agents";

const ACTIVE_STATUSES = new Set(["pending", "planning", "running", "awaiting_approval"]);
const REFRESH_DEBOUNCE_MS = 180;
const ACTIVE_POLL_MS = 2_000;

export function AgentRunActivity({
  runId,
  revision = 0,
  statusText,
}: {
  runId: string | null;
  revision?: number;
  statusText?: string | null;
}) {
  const [run, setRun] = useState<AgentRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestSequence = useRef(0);

  const load = useCallback(async () => {
    if (!runId) return;
    const sequence = ++requestSequence.current;
    const result = await getAgentRun(runId);
    if (sequence !== requestSequence.current) return;
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setError(null);
    setRun(result.data);
  }, [runId]);

  useEffect(() => {
    setRun(null);
    setError(null);
    if (!runId) return;
    void load();
  }, [load, runId]);

  useEffect(() => {
    if (!runId || revision === 0) return;
    const timer = window.setTimeout(() => void load(), REFRESH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [load, revision, runId]);

  useEffect(() => {
    if (!runId || !run || !ACTIVE_STATUSES.has(run.status)) return;
    const interval = window.setInterval(() => void load(), ACTIVE_POLL_MS);
    return () => window.clearInterval(interval);
  }, [load, run, runId]);

  if (!runId) return null;

  const visibleEvents = run?.events.slice(-6) ?? [];
  return (
    <section
      className="mx-6 mt-4 space-y-3 rounded-2xl border border-cyan-400/15 bg-[linear-gradient(145deg,rgba(8,47,73,.45),rgba(15,23,42,.7))] p-4"
      aria-live="polite"
      data-testid="agent-run-activity"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
            Multi-agent activity
          </p>
          <p className="mt-1 text-sm text-slate-300">
            {statusText ||
              (run
                ? "Coordinated specialists are working within bounded limits."
                : "Preparing a coordinated response…")}
          </p>
        </div>
        {run ? (
          <AgentRunStatusBadge status={run.status} />
        ) : (
          <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-300" aria-label="Loading run" />
        )}
      </div>

      {error ? (
        <div className="rounded-xl border border-amber-400/20 bg-amber-500/[0.07] p-3 text-sm text-amber-100" role="status">
          Agent activity is temporarily unavailable. The response can still continue.
          <button type="button" onClick={() => void load()} className="ml-2 underline underline-offset-2">
            Retry
          </button>
        </div>
      ) : null}

      {run?.safe_plan_summary || run?.tasks.length ? (
        <AgentPlanCard summary={run.safe_plan_summary} tasks={run.tasks} />
      ) : null}

      {run?.approvals.map((approval) => (
        <AgentApprovalCard key={approval.id} approval={approval} onResolved={() => void load()} />
      ))}

      {visibleEvents.length ? (
        <details className="rounded-xl border border-white/10 bg-slate-950/25 p-3">
          <summary className="cursor-pointer text-sm font-medium text-slate-200">Recent activity</summary>
          <div className="mt-3">
            <AgentTimeline events={visibleEvents} />
          </div>
        </details>
      ) : null}

      {run?.status === "cancelled" ? (
        <p className="rounded-xl bg-slate-950/40 p-3 text-sm text-slate-200">
          Coordinated response cancelled
        </p>
      ) : null}
    </section>
  );
}
