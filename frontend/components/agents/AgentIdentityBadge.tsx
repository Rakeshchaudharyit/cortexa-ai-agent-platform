const IDENTITIES: Record<string, { label: string; tone: string; symbol: string }> = {
  coordinator: { label: "Coordinator", tone: "text-cyan-200 ring-cyan-400/30", symbol: "C" },
  planning: { label: "Planning Agent", tone: "text-violet-200 ring-violet-400/30", symbol: "P" },
  knowledge: { label: "Knowledge Agent", tone: "text-blue-200 ring-blue-400/30", symbol: "K" },
  memory: { label: "Memory Agent", tone: "text-amber-200 ring-amber-400/30", symbol: "M" },
  tool: { label: "Tool Agent", tone: "text-emerald-200 ring-emerald-400/30", symbol: "T" },
  safety: { label: "Safety Agent", tone: "text-rose-200 ring-rose-400/30", symbol: "S" },
  conversation: { label: "Conversation Agent", tone: "text-teal-200 ring-teal-400/30", symbol: "R" },
};

export function agentIdentity(key: string | null | undefined) {
  const normalized = key?.replace(/_agent$/, "") ?? "coordinator";
  return IDENTITIES[normalized] ?? {
    label: normalized.replaceAll("_", " ").replace(/\b\w/g, (value) => value.toUpperCase()),
    tone: "text-slate-200 ring-slate-400/30",
    symbol: normalized.slice(0, 1).toUpperCase() || "A",
  };
}

export function AgentIdentityBadge({ agentKey }: { agentKey: string | null | undefined }) {
  const identity = agentIdentity(agentKey);
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md bg-slate-950/50 px-2 py-1 text-xs ring-1 ${identity.tone}`}>
      <span aria-hidden="true" className="font-semibold">{identity.symbol}</span>
      {identity.label}
    </span>
  );
}
