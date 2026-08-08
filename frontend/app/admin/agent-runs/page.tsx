"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { DataTable } from "@/components/admin/DataTable";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { listAdminAgentRuns } from "@/services/agents";
import type { AdminAgentRunSummary, AgentRunStatus } from "@/types/agents";

const PAGE_SIZE = 25;
export default function AdminAgentRunsPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<AdminAgentRunSummary[]>([]);
  const [status, setStatus] = useState<AgentRunStatus | "">("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async (nextOffset: number) => { setLoading(true); const result = await listAdminAgentRuns({ status: status || undefined, offset: nextOffset, limit: PAGE_SIZE }); if (result.ok) { setRuns(result.data.items); setTotal(result.data.total); setOffset(result.data.offset); } setLoading(false); }, [status]);
  useEffect(() => { void load(0); }, [load]);
  return <div data-testid="admin-agent-runs-page"><AdminPageHeader title="Agent Runs" description="Safe operational metadata for bounded multi-agent executions. User prompts and private context are never shown." actions={<label className="text-xs text-slate-400">Status<select value={status} onChange={(event) => setStatus(event.target.value as AgentRunStatus | "")} className="ml-2 rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-white"><option value="">All</option>{["pending","planning","running","awaiting_approval","completed","failed","cancelled","timed_out"].map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label>} /><DataTable loading={loading} rows={runs} onRowClick={(run) => router.push(`/admin/agent-runs/${run.id}`)} columns={[
    { key: "id", header: "Run", render: (run) => <code className="text-xs text-cyan-200">{run.id.slice(0, 8)}</code> },
    { key: "user", header: "User", render: (run) => <code className="text-xs text-slate-400">{run.user_id.slice(0, 8)}…</code> },
    { key: "summary", header: "Request", render: (run) => run.original_request_summary },
    { key: "status", header: "Status", render: (run) => <StatusBadge status={run.status} /> },
    { key: "mode", header: "Mode", render: (run) => run.execution_mode.replaceAll("_", " ") },
    { key: "tasks", header: "Tasks / tools", render: (run) => `${run.task_count} / ${run.tool_calls_used}` },
    { key: "duration", header: "Duration", render: (run) => run.duration_ms == null ? "Active" : `${run.duration_ms} ms` },
    { key: "created", header: "Created", render: (run) => new Date(run.created_at).toLocaleString() },
  ]} /><div className="mt-5 flex justify-between"><button disabled={!offset} onClick={() => void load(Math.max(0, offset - PAGE_SIZE))} className="rounded-lg border border-white/10 px-3 py-2 text-sm disabled:opacity-40">Previous</button><span className="text-xs text-slate-500">{total ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total}` : "0 runs"}</span><button disabled={offset + PAGE_SIZE >= total} onClick={() => void load(offset + PAGE_SIZE)} className="rounded-lg border border-white/10 px-3 py-2 text-sm disabled:opacity-40">Next</button></div></div>;
}
