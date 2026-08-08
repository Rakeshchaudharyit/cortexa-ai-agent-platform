"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AgentApprovalCard } from "@/components/agents/AgentApprovalCard";
import { AgentPlanCard } from "@/components/agents/AgentPlanCard";
import { AgentRunSummary } from "@/components/agents/AgentRunSummary";
import { AgentTimeline } from "@/components/agents/AgentTimeline";
import { CancelRunDialog } from "@/components/agents/CancelRunDialog";
import { RunErrorState } from "@/components/agents/RunErrorState";
import { cancelAgentRun, getAgentRun } from "@/services/agents";
import type { AgentRunDetail } from "@/types/agents";

const ACTIVE = new Set(["pending", "planning", "running", "awaiting_approval"]);
const POLL_INTERVAL_MS = 1500;

export default function AgentRunDetailPage() {
  const runId = String(useParams<{ runId: string }>().runId);
  const [run, setRun] = useState<AgentRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const requestInFlight = useRef(false);

  const load = useCallback(async (background = false) => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    const result = await getAgentRun(runId);
    requestInFlight.current = false;
    if (!background) setLoading(false);
    if (!result.ok) {
      setNotFound(result.status === 404);
      setError(result.error);
      return;
    }
    setNotFound(false);
    setError(null);
    setRun(result.data);
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!run || !ACTIVE.has(run.status)) return;
    const timer = window.setInterval(() => {
      void load(true);
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [load, run]);

  useEffect(() => {
    if (!run || !ACTIVE.has(run.status)) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [run]);

  if (loading) {
    return <main id="main-content" tabIndex={-1} className="mx-auto max-w-5xl p-8 text-sm text-slate-400">Restoring session and loading run…</main>;
  }
  if (!run) {
    return <main className="mx-auto max-w-5xl p-8"><RunErrorState notFound={notFound} message={error || undefined} /></main>;
  }

  const active = ACTIVE.has(run.status);
  const elapsedSeconds = Math.max(0, Math.floor((now - new Date(run.created_at).getTime()) / 1000));

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6" data-testid="agent-run-detail-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href="/agent-runs" className="text-sm text-cyan-300">← Agent Runs</Link>
        <div className="flex items-center gap-2">
          {active ? <span className="text-xs text-cyan-200" data-testid="agent-run-live-indicator">Live · {elapsedSeconds}s · updating automatically</span> : null}
          {run.conversation_id ? (
            active ? (
              <span
                className="cursor-not-allowed rounded-lg border border-white/5 px-3 py-2 text-sm text-slate-500"
                title="The final response is still being generated and saved"
                aria-disabled="true"
              >
                Response pending…
              </span>
            ) : (
              <Link href={`/chat/${run.conversation_id}`} className="rounded-lg border border-white/10 px-3 py-2 text-sm">Open conversation</Link>
            )
          ) : null}
          {active ? <button onClick={() => setDialog(true)} className="rounded-lg bg-rose-500/15 px-3 py-2 text-sm text-rose-100 ring-1 ring-rose-400/30">Cancel run</button> : null}
        </div>
      </div>
      <AgentRunSummary run={run} />
      {active && elapsedSeconds >= 45 ? (
        <section className="rounded-xl border border-amber-400/20 bg-amber-500/5 p-4" role="status">
          <p className="text-sm font-medium text-amber-100">Local AI is taking longer than expected.</p>
          <p className="mt-1 text-xs text-slate-400">This run is bounded and will fall back or stop rather than wait indefinitely.</p>
        </section>
      ) : null}
      <AgentPlanCard summary={run.safe_plan_summary} tasks={run.tasks} />
      {run.approvals.length ? <section><h2 className="mb-3 text-lg font-semibold text-white">Approvals</h2><div className="space-y-3">{run.approvals.map((approval) => <AgentApprovalCard key={approval.id} approval={approval} onResolved={() => void load()} />)}</div></section> : null}
      <section className="rounded-2xl border border-white/10 bg-slate-900/40 p-5"><h2 className="mb-4 text-lg font-semibold text-white">Activity timeline</h2><AgentTimeline events={run.events} /></section>
      {error ? <section className="rounded-xl border border-amber-400/20 bg-amber-500/5 p-4"><p className="text-sm text-amber-100">Live refresh issue: {error}</p></section> : null}
      {run.error_code ? <section className="rounded-xl border border-rose-400/20 bg-rose-500/5 p-4"><p className="text-sm font-medium text-rose-100">{run.safe_error_message || "Execution could not be completed"}</p><p className="mt-1 text-xs text-slate-500">Code: {run.error_code}</p></section> : null}
      <CancelRunDialog open={dialog} busy={cancelling} onCancel={() => setDialog(false)} onConfirm={() => { if (cancelling) return; setCancelling(true); void (async () => { const result = await cancelAgentRun(run.id); setCancelling(false); setDialog(false); if (result.ok) setRun(result.data); else setError(result.error); })(); }} />
    </main>
  );
}
