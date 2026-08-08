"use client";

import { useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { DataTable } from "@/components/admin/DataTable";
import { FilterBar, FilterInput, FilterSelect } from "@/components/admin/FilterBar";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { fetchAdminToolExecutions } from "@/services/admin";

export default function Page(){
  const [rows,setRows]=useState<Record<string,unknown>[]>([]);const[loading,setLoading]=useState(true);const[q,setQ]=useState("");const[status,setStatus]=useState("");const[total,setTotal]=useState(0);
  useEffect(()=>{let cancelled=false;void(async()=>{setLoading(true);const params:Record<string,string|number|undefined>={limit:50};if(status)params.status=status;if(q)params.tool_name=q;const result=await fetchAdminToolExecutions(params);if(cancelled)return;if(result.ok){setRows(result.data.items as Record<string,unknown>[]);setTotal(result.data.total);}else{setRows([]);setTotal(0);}setLoading(false);})();return()=>{cancelled=true;};},[q,status]);
  return <div className="space-y-6" data-testid="admin-tool-executions-page"><AdminPageHeader title="Tool Activity" description="Review privacy-safe execution metadata for server tools without exposing tool arguments or sensitive payloads."/><section className="rounded-3xl border border-white/8 bg-gradient-to-br from-slate-900/70 to-slate-950/60 p-5"><div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300/80">Execution telemetry</p><h3 className="mt-1 text-lg font-semibold text-white">Tool operations</h3><p className="mt-1 text-sm text-slate-400">Use this view to diagnose reliability and usage patterns without exposing request content.</p></div><div className="rounded-2xl border border-white/8 bg-black/20 px-4 py-3"><p className="text-xs uppercase tracking-wide text-slate-500">Visible executions</p><p className="mt-1 text-2xl font-semibold text-white">{total}</p></div></div></section><section className="rounded-2xl border border-white/8 bg-slate-900/40 p-4"><FilterBar><FilterInput placeholder="Search tool name" value={q} onChange={(e)=>setQ(e.target.value)} data-testid="admin-tool-executions-search"/><FilterSelect value={status} onChange={(e)=>setStatus(e.target.value)} data-testid="admin-tool-executions-status-filter"><option value="">All statuses</option><option value="active">Active</option><option value="ready">Ready</option><option value="failed">Failed</option><option value="succeeded">Succeeded</option><option value="disabled">Disabled</option></FilterSelect><p className="ml-auto text-xs text-slate-500">{total} total</p></FilterBar></section><DataTable loading={loading} emptyTitle="No tool activity found" emptyDescription="Tool executions will appear here after enabled capabilities are used." rows={rows.map((r,index)=>({...r,id:String(r.id??index)})) as Array<Record<string,unknown>&{id:string}>} columns={[
    {key:"primary",header:"Tool",render:(r)=><div><p className="font-medium text-white">{String(r.tool_name??r.safe_summary??"—")}</p><p className="mt-0.5 text-xs text-slate-500">Execution metadata</p></div>},
    {key:"owner",header:"User",render:(r)=>String(r.owner_email??r.user_email??r.actor_email??"System")},
    {key:"status",header:"Status",render:(r)=><StatusBadge status={String(r.status??"unknown")}/>},
    {key:"duration",header:"Duration",render:(r)=>r.duration_ms==null?"—":`${Number(r.duration_ms).toLocaleString()} ms`},
    {key:"created",header:"Started",render:(r)=>new Date(String(r.started_at??r.created_at??Date.now())).toLocaleString()},
  ]}/></div>;
}
