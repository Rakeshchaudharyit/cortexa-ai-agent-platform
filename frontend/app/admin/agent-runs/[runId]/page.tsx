"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AgentPlanCard } from "@/components/agents/AgentPlanCard";
import { AgentRunSummary } from "@/components/agents/AgentRunSummary";
import { AgentTimeline } from "@/components/agents/AgentTimeline";
import { AgentApprovalCard } from "@/components/agents/AgentApprovalCard";
import { RunErrorState } from "@/components/agents/RunErrorState";
import { getAdminAgentRun } from "@/services/agents";
import type { AdminAgentRunDetail } from "@/types/agents";

export default function AdminAgentRunDetailPage() {
  const runId = String(useParams<{ runId: string }>().runId);
  const [run, setRun] = useState<AdminAgentRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { void (async () => { const result = await getAdminAgentRun(runId); if (result.ok) setRun(result.data); else setError(result.error); })(); }, [runId]);
  if (!run) return error ? <RunErrorState message={error} /> : <p className="text-sm text-slate-400">Loading run…</p>;
  return <div className="space-y-6" data-testid="admin-agent-run-detail"><Link href="/admin/agent-runs" className="text-sm text-cyan-300">← Agent Runs</Link><AgentRunSummary run={run} /><section className="grid gap-3 rounded-2xl border border-white/10 bg-slate-900/40 p-5 text-sm sm:grid-cols-2 lg:grid-cols-4"><div><p className="text-xs text-slate-500">User ID</p><code className="break-all text-xs">{run.user_id}</code></div><div><p className="text-xs text-slate-500">Conversation</p>{run.conversation_id ? <Link href={`/admin/conversations`} className="break-all text-xs text-cyan-300">{run.conversation_id}</Link> : "—"}</div><div><p className="text-xs text-slate-500">Correlation ID</p><code className="break-all text-xs">{run.correlation_id}</code></div><div><p className="text-xs text-slate-500">Error</p><span className="text-xs">{run.error_code || "None"}</span></div></section><AgentPlanCard summary={run.safe_plan_summary} tasks={run.tasks} />{run.approvals.length ? <section><h2 className="mb-3 text-lg font-semibold">Approval history</h2><div className="space-y-3">{run.approvals.map((approval) => <AgentApprovalCard key={approval.id} approval={approval} readOnly />)}</div></section> : null}<section className="rounded-2xl border border-white/10 bg-slate-900/40 p-5"><h2 className="mb-4 text-lg font-semibold">Safe event timeline</h2><AgentTimeline events={run.events} /></section></div>;
}
