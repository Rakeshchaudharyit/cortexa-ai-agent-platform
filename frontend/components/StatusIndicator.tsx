import type { DependencyCheck } from "@/types/api";

type StatusTone = "ok" | "error" | "pending" | "unknown";

const toneStyles: Record<StatusTone, string> = {
  ok: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  error: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  pending: "bg-amber-500/15 text-amber-200 ring-amber-500/30",
  unknown: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
};

const dotStyles: Record<StatusTone, string> = {
  ok: "bg-emerald-400",
  error: "bg-rose-400",
  pending: "bg-amber-400 animate-pulse",
  unknown: "bg-slate-400",
};

type StatusIndicatorProps = {
  label: string;
  tone: StatusTone;
  detail?: string;
};

export function StatusIndicator({ label, tone, detail }: StatusIndicatorProps) {
  return (
    <div
      className={`flex flex-col gap-1 rounded-xl px-4 py-3 ring-1 ${toneStyles[tone]}`}
      data-testid={`status-${label.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <div className="flex items-center gap-2 text-sm font-medium tracking-wide">
        <span className={`h-2.5 w-2.5 rounded-full ${dotStyles[tone]}`} aria-hidden />
        <span>{label}</span>
      </div>
      {detail ? <p className="pl-4 text-xs opacity-80">{detail}</p> : null}
    </div>
  );
}

export function toneFromCheck(check: DependencyCheck | undefined, loading: boolean): StatusTone {
  if (loading) {
    return "pending";
  }
  if (!check) {
    return "unknown";
  }
  return check.status === "ok" ? "ok" : "error";
}
