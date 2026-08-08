"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { fetchAdminSystem } from "@/services/admin";
import type { AdminSystemHealthResponse } from "@/types/admin";

export default function AdminSystemPage() {
  const [data, setData] = useState<AdminSystemHealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => { const result = await fetchAdminSystem(); if (!result.ok) { setError(result.error); setData(null); return; } setData(result.data); setError(null); }, []);
  useEffect(() => { void reload(); }, [reload]);
  const healthy = useMemo(() => data?.components.filter((item) => item.status === "ok").length ?? 0, [data]);
  const degraded = useMemo(() => data?.components.filter((item) => item.status !== "ok").length ?? 0, [data]);

  return <div className="space-y-6" data-testid="admin-system-page">
    <AdminPageHeader title="System Health" description="A privacy-safe operational view of the services that power Chat, RAG, background processing, and storage." actions={<button type="button" className="rounded-xl border border-cyan-400/25 bg-cyan-400/8 px-4 py-2.5 text-sm font-medium text-cyan-100 transition hover:bg-cyan-400/12" onClick={() => void reload()} data-testid="admin-system-refresh">Refresh status</button>} />
    {error ? <div className="rounded-xl border border-rose-400/25 bg-rose-500/8 px-4 py-3 text-sm text-rose-200">{error}</div> : null}
    {data ? <>
      <section className="rounded-3xl border border-white/8 bg-gradient-to-br from-slate-900/80 to-slate-950/70 p-5 sm:p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300/80">Platform availability</p><div className="mt-2 flex flex-wrap items-center gap-3"><h3 className="text-2xl font-semibold text-white">Operational status</h3><StatusBadge status={data.overall} /></div><p className="mt-2 max-w-2xl text-sm text-slate-400">Last refreshed {new Date(data.refreshed_at).toLocaleString()}. This page intentionally omits secrets, connection strings, and filesystem paths.</p></div><div className="grid grid-cols-2 gap-3"><div className="rounded-2xl border border-emerald-400/15 bg-emerald-500/5 px-4 py-3"><p className="text-xs uppercase tracking-wide text-emerald-300/70">Healthy</p><p className="mt-1 text-2xl font-semibold text-emerald-200">{healthy}</p></div><div className="rounded-2xl border border-amber-400/15 bg-amber-500/5 px-4 py-3"><p className="text-xs uppercase tracking-wide text-amber-300/70">Attention</p><p className="mt-1 text-2xl font-semibold text-amber-100">{degraded}</p></div></div></div>
      </section>
      <section><div className="mb-3"><h3 className="text-base font-semibold text-white">Service components</h3><p className="mt-1 text-sm text-slate-500">Live health signals from configured infrastructure dependencies.</p></div><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.components.map((component) => <div key={component.name} className="rounded-2xl border border-white/8 bg-slate-900/45 p-5" data-testid="admin-system-component"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Service</p><h4 className="mt-1 font-medium capitalize text-white">{component.name.replaceAll("_", " ")}</h4></div><StatusBadge status={component.status} /></div>{component.message ? <p className="mt-4 text-sm leading-relaxed text-slate-300">{component.message}</p> : null}{component.detail ? <p className="mt-2 rounded-lg bg-black/20 px-3 py-2 text-xs leading-relaxed text-slate-500">{component.detail}</p> : null}</div>)}</div></section>
      {data.guidance.length ? <section className="rounded-2xl border border-cyan-400/10 bg-cyan-500/[0.035] p-5"><h3 className="text-sm font-semibold text-cyan-100">Operational guidance</h3><ul className="mt-3 space-y-2 text-sm text-slate-400">{data.guidance.map((item) => <li key={item} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400" /><span>{item}</span></li>)}</ul></section> : null}
    </> : <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="admin-system-loading">{Array.from({length:6}).map((_, index) => <div key={index} className="h-36 animate-pulse rounded-2xl bg-slate-800/35" />)}</div>}
  </div>;
}
