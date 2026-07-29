type CapabilityCardProps = {
  title: string;
  description: string;
};

export function CapabilityCard({ title, description }: CapabilityCardProps) {
  return (
    <article
      className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"
      data-testid="capability-card"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-base font-semibold text-slate-100">{title}</h3>
        <span
          className="shrink-0 rounded-md bg-slate-700/60 px-2 py-1 text-[11px] font-medium uppercase tracking-wider text-slate-300"
          data-testid="coming-later-badge"
        >
          Coming later
        </span>
      </div>
      <p className="text-sm leading-relaxed text-slate-400">{description}</p>
    </article>
  );
}

export const PLANNED_CAPABILITIES: CapabilityCardProps[] = [
  {
    title: "AI Agent",
    description: "Conversational agents with session continuity — not available in Phase 4.",
  },
  {
    title: "Chat Interface",
    description:
      "Product chat UI is intentionally deferred. Phase 4 focuses on documents and grounded Q&A.",
  },
  {
    title: "Agent Memory",
    description: "Short- and long-term memory services — not implemented yet.",
  },
  {
    title: "Agent Tools",
    description: "Permissioned tool calling — not implemented yet.",
  },
  {
    title: "Voice Interaction",
    description: "Local speech-to-text and text-to-speech — not implemented yet.",
  },
];
