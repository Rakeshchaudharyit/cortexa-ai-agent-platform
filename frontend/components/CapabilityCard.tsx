export type CapabilityStatus =
  | "online"
  | "available"
  | "healthy"
  | "unavailable"
  | "disabled"
  | "coming_later";

export type CapabilityCardProps = {
  title: string;
  description: string;
  status: CapabilityStatus;
  secondary?: string;
  testId?: string;
};

const STATUS_LABEL: Record<CapabilityStatus, string> = {
  online: "Online",
  available: "Available",
  healthy: "Healthy",
  unavailable: "Unavailable",
  disabled: "Disabled",
  coming_later: "Coming later",
};

const STATUS_STYLE: Record<CapabilityStatus, string> = {
  online: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  available: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  healthy: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  unavailable: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  disabled: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
  coming_later: "bg-slate-700/60 text-slate-300 ring-slate-500/30",
};

export function CapabilityCard({
  title,
  description,
  status,
  secondary,
  testId,
}: CapabilityCardProps) {
  return (
    <article
      className="flex h-full flex-col rounded-2xl border border-white/10 bg-white/[0.03] p-5"
      data-testid={testId ?? "capability-card"}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <h3 className="text-base font-semibold text-slate-100">{title}</h3>
        <span
          className={`shrink-0 rounded-md px-2 py-1 text-[11px] font-medium uppercase tracking-wider ring-1 ${STATUS_STYLE[status]}`}
          data-testid="capability-status-badge"
        >
          {STATUS_LABEL[status]}
        </span>
      </div>
      <p className="text-sm leading-relaxed text-slate-300">{description}</p>
      {secondary ? (
        <p className="mt-auto pt-3 text-xs leading-relaxed text-slate-500">{secondary}</p>
      ) : null}
    </article>
  );
}

/** Upcoming (not yet shipped) capabilities — not shown as live platform cards. */
export const UPCOMING_CAPABILITIES: CapabilityCardProps[] = [
  {
    title: "Long-term Memory",
    description: "Cross-conversation and profile memory across sessions.",
    status: "coming_later",
  },
  {
    title: "Voice Interaction",
    description: "Local speech-to-text and text-to-speech.",
    status: "coming_later",
  },
];
