"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { NewAgentRunDialog } from "@/components/agents/NewAgentRunDialog";
import { AgentRunStatusBadge } from "@/components/agents/AgentRunStatusBadge";
import { RunEmptyState } from "@/components/agents/RunEmptyState";
import { listAgentRuns } from "@/services/agents";
import type { AgentRunStatus, AgentRunSummary } from "@/types/agents";

const PAGE_SIZE = 12;
export default function AgentRunsPage() {
  const [runs, setRuns] = useState<AgentRunSummary[]>([]);
  const [status, setStatus] = useState<AgentRunStatus | "">("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newRunOpen, setNewRunOpen] = useState(false);
  const load = useCallback(async (nextOffset: number) => {
    setLoading(true); setError(null);
    const result = await listAgentRuns({ status: status || undefined, offset: nextOffset, limit: PAGE_SIZE });
    setLoading(false);
    if (!result.ok) { setError(result.error); return; }
    setRuns(result.data.items); setTotal(result.data.total); setOffset(result.data.offset);
  }, [status]);
  useEffect(() => { void load(0); }, [load]);
  return <main id="main-content" tabIndex={-1} className="mx-auto max-w-6xl px-4 py-8 sm:px-6" data-testid="agent-runs-page">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[.2em] text-cyan-300">Execution workspace</p><h1 className="mt-2 text-3xl font-semibold text-white">Agent Runs</h1><p className="mt-2 max-w-2xl text-sm text-slate-400">Start coordinated AI work, follow live execution, manage approvals, and review outcomes.</p></div><div className="flex flex-wrap items-center gap-3"><button type="button" onClick={() => setNewRunOpen(true)} className="rounded-lg bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300">+ New Agent Run</button><label className="text-xs text-slate-400">Status<select value={status} onChange={(event) => setStatus(event.target.value as AgentRunStatus | "")} className="ml-2 rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"><option value="">All statuses</option>{["pending","planning","running","awaiting_approval","completed","failed","cancelled","timed_out"].map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label></div></div>
    {error ? <p className="mt-6 rounded-xl border border-rose-400/20 bg-rose-500/10 p-3 text-sm text-rose-100" role="alert">{error}</p> : null}
    {loading ? <div className="mt-8 grid gap-4 md:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-44 animate-pulse rounded-2xl bg-slate-800/40" />)}</div> : runs.length === 0 ? <div className="mt-8"><RunEmptyState /></div> : <div className="mt-8 grid gap-4 md:grid-cols-2">{runs.map((run) => <article key={run.id} className="rounded-2xl border border-white/10 bg-slate-900/55 p-5 transition hover:border-cyan-400/25"><div className="flex items-start justify-between gap-3"><div><p className="text-xs text-slate-500">{new Date(run.created_at).toLocaleString()}</p><h2 className="mt-2 font-semibold text-slate-100">{run.original_request_summary}</h2></div><AgentRunStatusBadge status={run.status} /></div><dl className="mt-4 grid grid-cols-3 gap-2 text-xs"><div><dt className="text-slate-500">Tasks</dt><dd className="text-slate-200">{run.task_count}</dd></div><div><dt className="text-slate-500">Tools</dt><dd className="text-slate-200">{run.tool_calls_used}</dd></div><div><dt className="text-slate-500">Duration</dt><dd className="text-slate-200">{run.duration_ms == null ? "Active" : `${run.duration_ms} ms`}</dd></div></dl><Link href={`/agent-runs/${run.id}`} className="mt-5 inline-flex min-h-10 items-center text-sm font-medium text-cyan-300 hover:text-cyan-200">View run →</Link></article>)}</div>}
    <div className="mt-7 flex items-center justify-between"><button disabled={offset === 0 || loading} onClick={() => void load(Math.max(0, offset - PAGE_SIZE))} className="rounded-lg border border-white/10 px-4 py-2 text-sm disabled:opacity-40">Previous</button><span className="text-xs text-slate-500">{total ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total}` : "0 runs"}</span><button disabled={offset + PAGE_SIZE >= total || loading} onClick={() => void load(offset + PAGE_SIZE)} className="rounded-lg border border-white/10 px-4 py-2 text-sm disabled:opacity-40">Next</button></div>
    <NewAgentRunDialog open={newRunOpen} onClose={() => setNewRunOpen(false)} />
  </main>;
}
