"use client";

import { useEffect, useMemo, useState } from "react";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { DataTable } from "@/components/admin/DataTable";
import { ActionResultToast } from "@/components/admin/DeletionDialogs";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { fetchAdminTools, patchAdminTool, resetAdminToolConfiguration } from "@/services/admin";
import type { AdminToolSummary } from "@/types/admin";

export default function AdminToolsPage() {
  const [tools,setTools]=useState<AdminToolSummary[]>([]); const [loading,setLoading]=useState(true); const [pending,setPending]=useState<AdminToolSummary|null>(null); const [resetTarget,setResetTarget]=useState<AdminToolSummary|null>(null); const [toast,setToast]=useState<{message:string;tone:"success"|"error"}|null>(null);
  async function reload(){setLoading(true);const result=await fetchAdminTools();if(result.ok)setTools(result.data.tools);setLoading(false);} useEffect(()=>{void reload();},[]);
  const enabled=useMemo(()=>tools.filter((tool)=>tool.enabled).length,[tools]); const executions=useMemo(()=>tools.reduce((sum,tool)=>sum+tool.execution_count,0),[tools]);
  return <div className="space-y-6" data-testid="admin-tools-page">
    <AdminPageHeader title="Tool Registry" description="Control server-side capabilities available to AI workflows, with explicit enablement, confirmation policy, and execution visibility." />
    <ActionResultToast message={toast?.message??null} tone={toast?.tone}/>
    <div className="grid gap-3 sm:grid-cols-3"><div className="rounded-2xl border border-white/8 bg-slate-900/50 p-4"><p className="text-xs uppercase tracking-wide text-slate-500">Registered tools</p><p className="mt-2 text-2xl font-semibold text-white">{tools.length}</p></div><div className="rounded-2xl border border-white/8 bg-slate-900/50 p-4"><p className="text-xs uppercase tracking-wide text-slate-500">Enabled</p><p className="mt-2 text-2xl font-semibold text-emerald-200">{enabled}</p></div><div className="rounded-2xl border border-white/8 bg-slate-900/50 p-4"><p className="text-xs uppercase tracking-wide text-slate-500">Executions</p><p className="mt-2 text-2xl font-semibold text-cyan-200">{executions.toLocaleString()}</p></div></div>
    <DataTable loading={loading} rows={tools.map((t)=>({...t,id:t.name}))} emptyTitle="No registered tools" emptyDescription="Tools registered by the server will appear here." columns={[
      {key:"name",header:"Tool",render:(t)=><div><p className="font-medium text-white">{t.name}</p><p className="mt-0.5 max-w-md text-xs text-slate-500">{t.description}</p></div>},
      {key:"category",header:"Category",render:(t)=><span className="capitalize text-slate-300">{t.category}</span>},
      {key:"enabled",header:"Availability",render:(t)=><StatusBadge status={t.enabled?"active":"disabled"}/>},
      {key:"policy",header:"Policy",render:(t)=><div className="text-xs text-slate-300"><p>{t.confirmation_required?"Confirmation required":"Direct execution"}</p><p className="mt-0.5 text-slate-500">Timeout {t.timeout_seconds}s</p></div>},
      {key:"stats",header:"Reliability",render:(t)=><div className="text-xs text-slate-300"><p>{t.execution_count.toLocaleString()} executions</p><p className="mt-0.5 text-slate-500">{t.success_rate==null?"No success data":`${Math.round(t.success_rate*100)}% success`}</p></div>},
      {key:"actions",header:"",render:(t)=><div className="flex flex-wrap gap-2"><button type="button" className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${t.enabled?"border-rose-400/20 text-rose-200 hover:bg-rose-500/8":"border-cyan-400/20 text-cyan-200 hover:bg-cyan-500/8"}`} data-testid={`admin-tool-toggle-${t.name}`} onClick={()=>setPending(t)}>{t.enabled?"Disable":"Enable"}</button>{t.has_configuration?<button type="button" className="rounded-lg border border-amber-400/20 px-3 py-1.5 text-xs font-medium text-amber-200 hover:bg-amber-500/8" data-testid={`admin-tool-reset-${t.name}`} onClick={()=>setResetTarget(t)}>Reset config</button>:null}</div>},
    ]}/>
    <ConfirmDialog open={pending!==null} title={pending?.enabled?"Disable tool":"Enable tool"} message={`This changes availability of '${pending?.name}' for all users and is audited.`} danger={Boolean(pending?.enabled)} onCancel={()=>setPending(null)} onConfirm={()=>{if(!pending)return;void(async()=>{const result=await patchAdminTool(pending.name,{enabled:!pending.enabled});setToast(result.ok?{message:`Updated ${pending.name}`,tone:"success"}:{message:result.error,tone:"error"});setPending(null);await reload();})();}}/>
    <ConfirmDialog open={resetTarget!==null} title="Reset configuration" message={`Remove the persisted override for '${resetTarget?.name}' and restore server registry defaults.`} confirmLabel="Reset configuration" onCancel={()=>setResetTarget(null)} onConfirm={()=>{if(!resetTarget)return;void(async()=>{const result=await resetAdminToolConfiguration(resetTarget.name);setToast(result.ok?{message:`Reset configuration for ${resetTarget.name}`,tone:"success"}:{message:result.error,tone:"error"});setResetTarget(null);await reload();})();}}/>
  </div>;
}
