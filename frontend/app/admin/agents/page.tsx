"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { DataTable } from "@/components/admin/DataTable";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { listAdminAgents, updateAdminAgent } from "@/services/agents";
import type { AgentDefinition } from "@/types/agents";

export default function AdminAgentsPage() {
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [target, setTarget] = useState<AgentDefinition | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  async function reload() { setLoading(true); const result = await listAdminAgents(); if (result.ok) setAgents(result.data.items); setLoading(false); }
  useEffect(() => { void reload(); }, []);
  return <div data-testid="admin-agents-page"><AdminPageHeader title="Agents" description="Registered orchestration specialists with bounded, audited runtime configuration." />{message ? <p className="mb-4 rounded-lg border border-cyan-400/20 bg-cyan-500/10 p-3 text-sm text-cyan-100" role="status">{message}</p> : null}<DataTable loading={loading} rows={agents.map((agent) => ({ ...agent, id: agent.key }))} columns={[
    { key: "name", header: "Agent", render: (agent) => <div><Link href={`/admin/agents/${agent.key}`} className="font-medium text-cyan-200 hover:underline">{agent.display_name}</Link><p className="mt-1 max-w-xs text-xs text-slate-500">{agent.description}</p></div> },
    { key: "enabled", header: "Status", render: (agent) => <StatusBadge status={agent.enabled ? "active" : "disabled"} /> },
    { key: "kind", header: "Control", render: (agent) => agent.required_for_multi_agent ? <span className="text-xs text-amber-200">Required</span> : <span className="text-xs text-slate-400">Optional</span> },
    { key: "limits", header: "Limits", render: (agent) => <span className="text-xs">{agent.maximum_steps} steps · {agent.timeout_seconds}s</span> },
    { key: "capabilities", header: "Capabilities", render: (agent) => <span className="text-xs text-slate-400">{agent.capabilities.join(", ")}</span> },
    { key: "action", header: "", render: (agent) => <button type="button" disabled={agent.required_for_multi_agent && agent.enabled} onClick={() => setTarget(agent)} className="text-sm text-cyan-300 disabled:cursor-not-allowed disabled:text-slate-600" aria-label={`${agent.enabled ? "Disable" : "Enable"} ${agent.display_name}`}>{agent.enabled ? "Disable" : "Enable"}</button> },
  ]} /><ConfirmDialog open={target !== null} title={`${target?.enabled ? "Disable" : "Enable"} optional agent`} message={`This bounded configuration change for ${target?.display_name ?? "the agent"} is audited.`} danger={target?.enabled} onCancel={() => setTarget(null)} onConfirm={() => { if (!target) return; void (async () => { const result = await updateAdminAgent(target.key, { enabled: !target.enabled }); setMessage(result.ok ? `Updated ${target.display_name}. The audited setting is active.` : result.error); setTarget(null); await reload(); })(); }} /></div>;
}
