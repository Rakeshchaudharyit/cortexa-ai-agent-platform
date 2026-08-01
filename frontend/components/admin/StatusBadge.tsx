const STYLES: Record<string, string> = {
  ok: "bg-emerald-500/15 text-emerald-200 ring-emerald-400/30",
  ready: "bg-emerald-500/15 text-emerald-200 ring-emerald-400/30",
  active: "bg-emerald-500/15 text-emerald-200 ring-emerald-400/30",
  succeeded: "bg-emerald-500/15 text-emerald-200 ring-emerald-400/30",
  degraded: "bg-amber-500/15 text-amber-100 ring-amber-400/30",
  processing: "bg-amber-500/15 text-amber-100 ring-amber-400/30",
  pending: "bg-amber-500/15 text-amber-100 ring-amber-400/30",
  proposed: "bg-amber-500/15 text-amber-100 ring-amber-400/30",
  unavailable: "bg-rose-500/15 text-rose-100 ring-rose-400/30",
  failed: "bg-rose-500/15 text-rose-100 ring-rose-400/30",
  disabled: "bg-rose-500/15 text-rose-100 ring-rose-400/30",
  deleted: "bg-rose-500/15 text-rose-100 ring-rose-400/30",
  rejected: "bg-rose-500/15 text-rose-100 ring-rose-400/30",
  unknown: "bg-slate-500/15 text-slate-200 ring-slate-400/30",
  admin: "bg-cyan-500/15 text-cyan-100 ring-cyan-400/30",
  user: "bg-slate-500/15 text-slate-200 ring-slate-400/30",
};

export function StatusBadge({ status }: { status: string }) {
  const style = STYLES[status.toLowerCase()] || STYLES.unknown;
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ${style}`}
      data-testid="admin-status-badge"
    >
      {status}
    </span>
  );
}
