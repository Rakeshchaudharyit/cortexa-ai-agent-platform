"use client";

import { useEffect, useMemo, useState } from "react";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { DangerZone } from "@/components/admin/DangerZone";
import { ActionResultToast } from "@/components/admin/DeletionDialogs";
import { fetchAdminSettings, patchAdminSettings, resetAdminSetting } from "@/services/admin";
import type { AdminSettingItem } from "@/types/admin";

export default function AdminSettingsPage() {
  const [settings,setSettings]=useState<AdminSettingItem[]>([]); const [draft,setDraft]=useState(""); const [toast,setToast]=useState<{message:string;tone:"success"|"error"}|null>(null); const [resetKey,setResetKey]=useState<string|null>(null);
  async function reload(){ const result=await fetchAdminSettings(); if(!result.ok){setToast({message:result.error,tone:"error"});return;} setSettings(result.data.settings); const display=result.data.settings.find((s)=>s.key==="platform_display_name"); setDraft(String(display?.value??"")); }
  useEffect(()=>{void reload();},[]);
  const overrides=useMemo(()=>settings.filter((item)=>item.source==="override").length,[settings]);
  async function save(){setToast(null);const result=await patchAdminSettings({platform_display_name:draft});if(!result.ok){setToast({message:result.error,tone:"error"});return;}setToast({message:"Platform display name updated",tone:"success"});await reload();}
  return <div className="space-y-6" data-testid="admin-settings-page">
    <AdminPageHeader title="Platform Settings" description="Manage allowlisted workspace settings while keeping credentials and security-sensitive configuration outside the UI." />
    <ActionResultToast message={toast?.message??null} tone={toast?.tone}/>
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(280px,.6fr)]">
      <section className="rounded-2xl border border-white/8 bg-slate-900/50 p-5"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-300/80">Workspace identity</p><h3 className="mt-1 text-lg font-semibold text-white">Display name</h3><p className="mt-1 text-sm text-slate-400">This is the safe product label presented to users. It does not affect internal service identifiers.</p><label className="mt-5 block text-sm font-medium text-slate-300" htmlFor="platform_display_name">Platform display name</label><input id="platform_display_name" className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950/70 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-400/40" value={draft} onChange={(e)=>setDraft(e.target.value)} data-testid="admin-settings-display-name"/><button type="button" className="mt-4 rounded-xl bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-cyan-300" onClick={()=>void save()} data-testid="admin-settings-save">Save changes</button></section>
      <aside className="rounded-2xl border border-white/8 bg-slate-900/40 p-5"><p className="text-xs uppercase tracking-wide text-slate-500">Configuration posture</p><p className="mt-2 text-3xl font-semibold text-white">{overrides}</p><p className="mt-1 text-sm text-slate-400">Database override{overrides===1?"":"s"} active</p><div className="mt-5 rounded-xl border border-emerald-400/15 bg-emerald-500/5 p-3 text-xs leading-relaxed text-emerald-100/80">Secrets, credentials, and production security flags remain blocked from this admin surface.</div></aside>
    </div>
    <section className="rounded-2xl border border-white/8 bg-slate-900/40 p-5"><div className="mb-4"><h3 className="text-sm font-semibold text-white">Safe configuration inventory</h3><p className="mt-1 text-xs text-slate-500">Source indicates whether a value comes from defaults, runtime configuration, or an explicit database override.</p></div><ul className="divide-y divide-white/5">{settings.map((item)=><li key={item.key} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><p className="truncate text-sm font-medium text-slate-200">{item.key}</p><p className="mt-0.5 text-xs text-slate-500">{String(item.value)} · {item.source}</p></div>{item.source==="override"?<button type="button" className="w-fit rounded-lg border border-amber-400/20 px-3 py-1.5 text-xs font-medium text-amber-200 hover:bg-amber-500/8" data-testid={`admin-settings-reset-${item.key}`} onClick={()=>setResetKey(item.key)}>Reset to default</button>:<span className="text-xs text-slate-600">Managed by {item.source}</span>}</li>)}</ul></section>
    <div className="max-w-2xl"><DangerZone description="Resetting an override returns that setting to environment/default configuration. Audit history remains immutable."><p className="text-xs text-rose-100/60">Unsafe keys and audit records cannot be modified from this screen.</p></DangerZone></div>
    <ConfirmDialog open={resetKey!==null} title="Reset to default" message={`Remove the database override for '${resetKey}' and restore the environment/default value.`} confirmLabel="Reset to default" onCancel={()=>setResetKey(null)} onConfirm={()=>{if(!resetKey)return;void(async()=>{const result=await resetAdminSetting(resetKey);setResetKey(null);setToast(result.ok?{message:`Reset ${result.data.updated_keys.join(", ")} to default`,tone:"success"}:{message:result.error,tone:"error"});await reload();})();}}/>
  </div>;
}
