export function RunEmptyState() {
  return <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.02] p-10 text-center" data-testid="agent-runs-empty"><h2 className="text-lg font-semibold text-slate-100">No coordinated agent runs yet.</h2><p className="mt-2 text-sm text-slate-400">Ordinary simple chats use the fast response path and do not create Agent Runs.</p></div>;
}
