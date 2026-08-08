"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { bulkAdminJobs, cancelAdminJob, createAdminDemoJob, fetchAdminJobs, requeueAdminJob } from "@/services/admin";
import type { AdminBackgroundJob, AdminJobList } from "@/types/admin";

const TERMINAL = new Set(["succeeded", "failed", "dead_lettered", "cancelled"]);
const REQUEUEABLE = new Set(["failed", "dead_lettered"]);

function formatTime(value: string | null) { return value ? new Date(value).toLocaleString() : "—"; }
function formatAge(seconds: number | null | undefined) {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}
function statusClass(status: string) {
  if (status === "succeeded") return "bg-emerald-500/10 text-emerald-200 ring-emerald-400/25";
  if (status === "dead_lettered") return "bg-fuchsia-500/10 text-fuchsia-200 ring-fuchsia-400/25";
  if (status === "failed") return "bg-rose-500/10 text-rose-200 ring-rose-400/25";
  if (status === "cancelled") return "bg-slate-500/15 text-slate-300 ring-slate-400/20";
  if (status === "running") return "bg-cyan-500/10 text-cyan-100 ring-cyan-400/25";
  if (status === "retrying") return "bg-amber-500/10 text-amber-100 ring-amber-400/25";
  return "bg-sky-500/10 text-sky-100 ring-sky-400/25";
}

function OpsMetric({ label, value, detail, tone = "default" }: { label: string; value: string | number; detail?: string; tone?: "default" | "good" | "warn" | "bad" }) {
  const toneClass = tone === "good" ? "text-emerald-300" : tone === "warn" ? "text-amber-200" : tone === "bad" ? "text-rose-300" : "text-white";
  return <div className="rounded-2xl border border-white/8 bg-slate-900/55 p-4"><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</p><p className={`mt-2 text-2xl font-semibold ${toneClass}`}>{value}</p>{detail ? <p className="mt-1 text-xs text-slate-500">{detail}</p> : null}</div>;
}

export default function AdminJobsPage() {
  const [data, setData] = useState<AdminJobList | null>(null);
  const [filter, setFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const load = useCallback(async () => {
    const result = await fetchAdminJobs(filter || undefined, typeFilter || undefined);
    if (!result.ok) { setError(result.error); return; }
    setData(result.data); setError(null);
  }, [filter, typeFilter]);

  useEffect(() => { void load(); const timer = window.setInterval(() => void load(), 1500); return () => window.clearInterval(timer); }, [load]);
  useEffect(() => { const visible = new Set(data?.items.map((item) => item.id) ?? []); setSelected((current) => new Set([...current].filter((id) => visible.has(id)))); }, [data]);

  const activeCount = useMemo(() => data?.items.filter((job) => !TERMINAL.has(job.status)).length ?? 0, [data]);
  const selectedJobs = useMemo(() => data?.items.filter((job) => selected.has(job.id)) ?? [], [data, selected]);
  const allVisibleSelected = Boolean(data?.items.length) && data!.items.every((job) => selected.has(job.id));

  async function createDemo() { setCreating(true); setNotice(null); const result = await createAdminDemoJob(`demo-${crypto.randomUUID()}`); setCreating(false); if (!result.ok) { setError(result.error); return; } setNotice(`Validation job ${result.data.id.slice(0, 8)} queued successfully.`); await load(); }
  async function cancel(job: AdminBackgroundJob) { const result = await cancelAdminJob(job.id); if (!result.ok) { setError(result.error); return; } setNotice(`Cancellation requested for ${job.id.slice(0, 8)}.`); await load(); }
  async function requeue(job: AdminBackgroundJob) { const result = await requeueAdminJob(job.id); if (!result.ok) { setError(result.error); return; } setNotice(`Job ${job.id.slice(0, 8)} requeued.`); await load(); }
  async function runBulk(action: "cancel" | "requeue") {
    const ids = selectedJobs.filter((job) => action === "cancel" ? !TERMINAL.has(job.status) : REQUEUEABLE.has(job.status)).map((job) => job.id);
    if (!ids.length) { setNotice(`No selected jobs are eligible for ${action}.`); return; }
    setBulkBusy(true); const result = await bulkAdminJobs(ids, action); setBulkBusy(false);
    if (!result.ok) { setError(result.error); return; }
    setNotice(`${result.data.changed} job(s) updated; ${result.data.skipped} skipped.`); setSelected(new Set()); await load();
  }

  return <div className="min-w-0 space-y-6">
    <AdminPageHeader title="Background Jobs" description="Monitor durable AI workloads, queue pressure, retries, cancellation, and recovery from one operations console." actions={<button type="button" onClick={() => void createDemo()} disabled={creating || !data?.worker_healthy} className="rounded-xl bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-40">{creating ? "Queueing…" : "Run validation job"}</button>} />

    {notice ? <div role="status" aria-live="polite" className="rounded-xl border border-emerald-400/25 bg-emerald-500/8 px-4 py-3 text-sm text-emerald-100">{notice}</div> : null}
    {error ? <div role="alert" className="rounded-xl border border-rose-400/25 bg-rose-500/8 px-4 py-3 text-sm text-rose-100">{error}</div> : null}

    <section className="rounded-3xl border border-white/8 bg-gradient-to-br from-slate-900/80 to-slate-950/70 p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300/80">Queue reliability</p><h3 className="mt-1 text-lg font-semibold text-white">Worker and delivery health</h3><p className="mt-1 text-sm text-slate-400">Durable state is persisted in PostgreSQL; Redis is used for delivery and retry scheduling.</p></div><span className={`inline-flex w-fit rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ${data?.worker_healthy ? "bg-emerald-500/10 text-emerald-200 ring-emerald-400/25" : "bg-rose-500/10 text-rose-200 ring-rose-400/25"}`}>{data?.worker_healthy ? "Worker healthy" : "Worker unavailable"}</span></div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <OpsMetric label="Worker" value={data?.worker_healthy ? "Healthy" : "Offline"} detail={`Last seen ${formatTime(data?.worker_last_seen_at ?? null)}`} tone={data?.worker_healthy ? "good" : "bad"} />
        <OpsMetric label="Ready queue" value={data?.queue_metrics.ready_depth ?? 0} detail="Waiting for a worker" />
        <OpsMetric label="Delayed retries" value={data?.queue_metrics.delayed_depth ?? 0} detail="Backoff window" tone={(data?.queue_metrics.delayed_depth ?? 0) > 0 ? "warn" : "default"} />
        <OpsMetric label="Dead letter" value={data?.queue_metrics.dead_letter_count ?? 0} detail="Needs admin review" tone={(data?.queue_metrics.dead_letter_count ?? 0) > 0 ? "bad" : "default"} />
        <OpsMetric label="Active" value={activeCount} detail={`Stale ${data?.queue_metrics.stale_running_count ?? 0}`} tone={(data?.queue_metrics.stale_running_count ?? 0) > 0 ? "warn" : "default"} />
        <OpsMetric label="Oldest queued" value={formatAge(data?.queue_metrics.oldest_queued_age_seconds)} detail={`${data?.total ?? 0} total jobs`} />
      </div>
    </section>

    <section className="rounded-2xl border border-white/8 bg-slate-900/45 p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs font-medium uppercase tracking-wide text-slate-500" htmlFor="job-status">Status</label>
          <select id="job-status" value={filter} onChange={(event) => setFilter(event.target.value)} className="rounded-xl border border-white/10 bg-slate-950/70 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400/40"><option value="">All statuses</option><option value="queued">Queued</option><option value="running">Running</option><option value="retrying">Retrying</option><option value="succeeded">Succeeded</option><option value="failed">Legacy failed</option><option value="dead_lettered">Dead letter</option><option value="cancelled">Cancelled</option></select>
          <label className="text-xs font-medium uppercase tracking-wide text-slate-500" htmlFor="job-type">Workload</label>
          <select id="job-type" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} className="rounded-xl border border-white/10 bg-slate-950/70 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400/40"><option value="">All workloads</option><option value="document.ingestion">Document ingestion</option><option value="document.reindex">Document re-index</option><option value="evaluation.run">RAG evaluation</option><option value="evaluation.export">Evaluation export</option><option value="demo.validation">Validation demo</option></select>
        </div>
        {selected.size ? <div className="flex flex-wrap items-center gap-2 lg:ml-auto"><span className="text-xs text-slate-500">{selected.size} selected</span><button type="button" disabled={bulkBusy} onClick={() => void runBulk("cancel")} className="rounded-lg border border-rose-400/25 px-3 py-2 text-xs font-medium text-rose-200 hover:bg-rose-500/8 disabled:opacity-40">Cancel selected</button><button type="button" disabled={bulkBusy} onClick={() => void runBulk("requeue")} className="rounded-lg border border-cyan-400/25 px-3 py-2 text-xs font-medium text-cyan-200 hover:bg-cyan-500/8 disabled:opacity-40">Requeue failed</button></div> : null}
      </div>
    </section>

    <section className="min-w-0 overflow-hidden rounded-2xl border border-white/8 bg-slate-950/45">
      <div className="cx-scrollbar overflow-x-auto overscroll-x-contain">
        <table className="min-w-[980px] w-full divide-y divide-white/8 text-sm">
          <thead className="bg-white/[0.035] text-left text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500"><tr><th className="px-4 py-3"><input aria-label="Select all jobs" type="checkbox" checked={allVisibleSelected} onChange={(event) => setSelected(event.target.checked ? new Set(data?.items.map((job) => job.id) ?? []) : new Set())} /></th><th className="px-4 py-3">Workload</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Progress</th><th className="px-4 py-3">Attempts</th><th className="px-4 py-3">Created</th><th className="px-4 py-3">Actions</th></tr></thead>
          <tbody className="divide-y divide-white/5">
            {data?.items.map((job) => <tr key={job.id} className="align-top transition hover:bg-white/[0.025]"><td className="px-4 py-4"><input aria-label={`Select job ${job.id}`} type="checkbox" checked={selected.has(job.id)} onChange={(event) => setSelected((current) => { const next = new Set(current); if (event.target.checked) next.add(job.id); else next.delete(job.id); return next; })} /></td><td className="max-w-sm px-4 py-4"><p className="font-medium text-white">{job.job_type.replaceAll(".", " · ")}</p><p className="mt-1 font-mono text-[11px] text-slate-600">{job.id}</p>{job.resource_id ? <p className="mt-1 truncate text-xs text-cyan-300/70">{job.resource_type}: {job.resource_id}</p> : null}<p className="mt-2 text-xs leading-relaxed text-slate-400">{job.status_message ?? "Awaiting status update"}</p>{job.error_code ? <p className="mt-2 rounded-lg bg-rose-500/8 px-2.5 py-2 text-xs text-rose-200">{job.error_code}: {job.error_message ?? "Job failed"}</p> : null}</td><td className="px-4 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${statusClass(job.status)}`}>{job.status.replaceAll("_", " ")}</span></td><td className="min-w-44 px-4 py-4"><div className="h-2 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-teal-400 transition-all" style={{ width: `${job.progress_percent}%` }} /></div><p className="mt-2 text-xs text-slate-500">{job.progress_percent}%</p></td><td className="px-4 py-4 text-slate-300">{job.attempt_count}/{job.max_attempts}</td><td className="px-4 py-4 text-xs text-slate-400">{formatTime(job.created_at)}</td><td className="px-4 py-4"><div className="flex flex-wrap gap-2">{!TERMINAL.has(job.status) ? <button type="button" onClick={() => void cancel(job)} className="rounded-lg border border-rose-400/25 px-3 py-1.5 text-xs text-rose-200 hover:bg-rose-500/8">Cancel</button> : null}{REQUEUEABLE.has(job.status) ? <button type="button" onClick={() => void requeue(job)} className="rounded-lg border border-cyan-400/25 px-3 py-1.5 text-xs text-cyan-200 hover:bg-cyan-500/8">Requeue</button> : null}{job.status === "succeeded" || job.status === "cancelled" ? <span className="text-xs text-slate-600">No action required</span> : null}</div></td></tr>)}
            {!data?.items.length ? <tr><td colSpan={7} className="px-6 py-16 text-center"><p className="text-sm font-medium text-slate-300">No jobs match these filters</p><p className="mt-1 text-xs text-slate-500">Adjust the status or workload filter to review more execution history.</p></td></tr> : null}
          </tbody>
        </table>
      </div>
    </section>
  </div>;
}
