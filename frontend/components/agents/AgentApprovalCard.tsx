"use client";

import { useEffect, useState } from "react";
import { approveAgentApproval, rejectAgentApproval } from "@/services/agents";
import type { AgentApproval } from "@/types/agents";

export function AgentApprovalCard({ approval, onResolved, readOnly = false }: { approval: AgentApproval; onResolved?: (value: AgentApproval) => void; readOnly?: boolean }) {
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [current, setCurrent] = useState(approval);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setCurrent(approval);
  }, [approval]);

  async function resolve(action: "approve" | "reject") {
    if (busy || current.status !== "pending") return;
    setBusy(action);
    setError(null);
    const result = action === "approve" ? await approveAgentApproval(current.id) : await rejectAgentApproval(current.id);
    setBusy(null);
    if (!result.ok) { setError(result.error); return; }
    setCurrent(result.data);
    onResolved?.(result.data);
  }

  return (
    <section className="rounded-2xl border border-amber-400/25 bg-amber-500/[0.07] p-4" data-testid={`agent-approval-${current.id}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-200">Approval required</p>
      <h3 className="mt-2 text-sm font-semibold text-white">{current.action_type.replaceAll("_", " ")}</h3>
      <p className="mt-1 text-sm leading-relaxed text-slate-300">{current.safe_action_summary}</p>
      <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
        <span>Requested {new Date(current.requested_at).toLocaleString()}</span>
        {current.expires_at ? <span>Expires {new Date(current.expires_at).toLocaleString()}</span> : null}
      </div>
      {current.status === "pending" && !readOnly ? (
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <button type="button" disabled={busy !== null} onClick={() => void resolve("approve")} className="min-h-11 rounded-lg bg-cyan-500/20 px-4 py-2 text-sm font-medium text-cyan-100 ring-1 ring-cyan-400/40 disabled:opacity-50" aria-label="Approve and continue">
            {busy === "approve" ? "Approving…" : "Approve and continue"}
          </button>
          <button type="button" disabled={busy !== null} onClick={() => void resolve("reject")} className="min-h-11 rounded-lg bg-slate-800 px-4 py-2 text-sm text-slate-100 ring-1 ring-white/10 disabled:opacity-50" aria-label="Reject approval">
            {busy === "reject" ? "Rejecting…" : "Reject"}
          </button>
        </div>
      ) : <p className="mt-4 text-sm font-medium text-slate-200">{current.status === "approved" ? "Approved · Resuming…" : current.status.replaceAll("_", " ")}</p>}
      {error ? <p className="mt-3 text-sm text-rose-200" role="alert">{error}</p> : null}
    </section>
  );
}
