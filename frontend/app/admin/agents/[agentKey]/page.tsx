"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { getAdminAgent, updateAdminAgent } from "@/services/agents";
import type { AgentDefinition } from "@/types/agents";

export default function AdminAgentDetailPage() {
  const key = String(useParams<{ agentKey: string }>().agentKey);
  const [agent, setAgent] = useState<AgentDefinition | null>(null);
  const [timeout, setTimeoutValue] = useState(60);
  const [steps, setSteps] = useState(5);
  const [tools, setTools] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(async () => { const result = await getAdminAgent(key); if (result.ok) { setAgent(result.data); setTimeoutValue(result.data.timeout_seconds); setSteps(result.data.maximum_steps); setTools(result.data.allowed_tools); } else setMessage(result.error); }, [key]);
  useEffect(() => { void load(); }, [load]);
  if (!agent) return <div className="text-sm text-slate-400">{message || "Loading agent…"}</div>;
  const agentKey = agent.key;
  async function save() { if (timeout < 5 || timeout > 600) { setMessage("Timeout must be between 5 and 600 seconds."); return; } if (steps < 1 || steps > 32) { setMessage("Maximum steps must be between 1 and 32."); return; } const result = await updateAdminAgent(agentKey, { timeout_seconds: timeout, maximum_steps: steps, allowed_tools: tools }); setMessage(result.ok ? "Agent configuration saved and audited." : result.error); if (result.ok) setAgent(result.data); }
  return <div data-testid="admin-agent-detail"><Link href="/admin/agents" className="mb-4 inline-flex text-sm text-cyan-300">← Agents</Link><AdminPageHeader title={agent.display_name} description={agent.description} />{agent.required_for_multi_agent ? <div className="mb-5 rounded-xl border border-amber-400/20 bg-amber-500/[0.06] p-4"><p className="font-medium text-amber-100">Required system agent</p><p className="mt-1 text-sm text-slate-400">This agent cannot be disabled because it protects orchestration integrity.</p></div> : null}{message ? <p className="mb-5 rounded-lg border border-white/10 bg-white/5 p-3 text-sm" role="status">{message}</p> : null}<div className="grid gap-5 lg:grid-cols-2"><section className="rounded-2xl border border-white/10 bg-slate-900/40 p-5"><div className="flex justify-between"><h3 className="font-semibold text-white">Identity and role</h3><StatusBadge status={agent.enabled ? "active" : "disabled"} /></div><dl className="mt-4 space-y-3 text-sm"><div><dt className="text-slate-500">Version</dt><dd>{agent.version}</dd></div><div><dt className="text-slate-500">Capabilities</dt><dd className="mt-1 flex flex-wrap gap-2">{agent.capabilities.map((value) => <span key={value} className="rounded bg-cyan-500/10 px-2 py-1 text-xs text-cyan-100">{value}</span>)}</dd></div></dl></section><section className="rounded-2xl border border-white/10 bg-slate-900/40 p-5"><h3 className="font-semibold text-white">Bounded configuration</h3><div className="mt-4 grid gap-4 sm:grid-cols-2"><label className="text-xs text-slate-400">Timeout seconds<input type="number" min={5} max={600} value={timeout} onChange={(event) => setTimeoutValue(Number(event.target.value))} className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white" /></label><label className="text-xs text-slate-400">Maximum steps<input type="number" min={1} max={32} value={steps} onChange={(event) => setSteps(Number(event.target.value))} className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white" /></label></div><fieldset className="mt-4"><legend className="text-xs text-slate-400">Allowed tools (restrictions only)</legend><div className="mt-2 space-y-2">{agent.allowed_tools.length ? agent.allowed_tools.map((tool) => <label key={tool} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={tools.includes(tool)} onChange={(event) => setTools((current) => event.target.checked ? [...current, tool] : current.filter((value) => value !== tool))} />{tool}</label>) : <p className="text-sm text-slate-500">No tools allowed.</p>}</div></fieldset><button onClick={() => void save()} className="mt-5 rounded-lg bg-cyan-500/20 px-4 py-2 text-sm font-medium text-cyan-100 ring-1 ring-cyan-400/30">Save configuration</button></section></div></div>;
}
