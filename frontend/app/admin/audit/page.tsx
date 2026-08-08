"use client";

import { useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { DataTable } from "@/components/admin/DataTable";
import { FilterBar, FilterInput, FilterSelect } from "@/components/admin/FilterBar";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { fetchAdminAudit } from "@/services/admin";

export default function Page() {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [total, setTotal] = useState(0);
  useEffect(() => { let cancelled = false; void (async () => { setLoading(true); const params: Record<string,string|number|undefined> = { limit:50 }; if(status) params.status=status; if(q) params.action=q; const result=await fetchAdminAudit(params); if(cancelled) return; if(result.ok){setRows(result.data.items as Record<string,unknown>[]);setTotal(result.data.total);} else {setRows([]);setTotal(0);} setLoading(false); })(); return()=>{cancelled=true;}; },[q,status]);
  return <div className="space-y-6" data-testid="admin-audit-page">
    <AdminPageHeader title="Audit Logs" description="Review privacy-safe administrative activity and operational changes across the workspace." />
    <section className="rounded-3xl border border-white/8 bg-gradient-to-br from-slate-900/70 to-slate-950/60 p-5"><div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300/80">Governance trail</p><h3 className="mt-1 text-lg font-semibold text-white">Administrative activity</h3><p className="mt-1 text-sm text-slate-400">Event metadata is retained for traceability without exposing secrets or sensitive payloads.</p></div><div className="rounded-2xl border border-white/8 bg-black/20 px-4 py-3"><p className="text-xs uppercase tracking-wide text-slate-500">Visible events</p><p className="mt-1 text-2xl font-semibold text-white">{total}</p></div></div></section>
    <section className="rounded-2xl border border-white/8 bg-slate-900/40 p-4"><FilterBar><FilterInput placeholder="Search action" value={q} onChange={(e)=>setQ(e.target.value)} data-testid="admin-audit-search"/><FilterSelect value={status} onChange={(e)=>setStatus(e.target.value)} data-testid="admin-audit-status-filter"><option value="">All statuses</option><option value="active">Active</option><option value="ready">Ready</option><option value="failed">Failed</option><option value="succeeded">Succeeded</option><option value="disabled">Disabled</option></FilterSelect><p className="ml-auto text-xs text-slate-500">{total} events</p></FilterBar></section>
    <DataTable loading={loading} emptyTitle="No audit events found" emptyDescription="Try a broader action or status filter." rows={rows.map((r,index)=>({...r,id:String(r.id??index)})) as Array<Record<string,unknown>&{id:string}>} columns={[
      {key:"primary",header:"Activity",render:(r)=> <div><p className="font-medium text-white">{String(r.action??r.safe_summary??r.filename??r.title??r.tool_name??"—")}</p><p className="mt-0.5 max-w-xl truncate text-xs text-slate-500">{String(r.safe_summary??r.target_type??"Administrative event")}</p></div>},
      {key:"owner",header:"Actor",render:(r)=>String(r.owner_email??r.user_email??r.actor_email??"System")},
      {key:"status",header:"Type",render:(r)=><StatusBadge status={String(r.target_type??r.action??"event")}/>},
      {key:"created",header:"Timestamp",render:(r)=>new Date(String(r.created_at??r.started_at??Date.now())).toLocaleString()},
    ]}/>
  </div>;
}
