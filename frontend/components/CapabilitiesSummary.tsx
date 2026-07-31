const CAPABILITIES = [
  "Local Ollama-powered AI",
  "Secure registration and login",
  "Session restoration after refresh",
  "Document upload and vector indexing",
  "Citation-based RAG answers",
  "Persistent multi-turn conversations",
  "Native Ollama tool calling",
  "Auditable tool executions",
  "User-controlled long-term memory",
  "Role and ownership enforcement",
  "Isolated development and test databases",
] as const;

export function CapabilitiesSummary() {
  return (
    <section className="flex flex-col gap-4" data-testid="capabilities-summary">
      <div>
        <h2 className="text-lg font-semibold text-slate-100">Project capabilities</h2>
        <p className="mt-1 text-sm text-slate-400">
          What this Phase 7 local platform delivers today.
        </p>
      </div>
      <ul className="grid gap-2 sm:grid-cols-2">
        {CAPABILITIES.map((item) => (
          <li
            key={item}
            className="flex items-start gap-2 text-sm text-slate-300"
            data-testid="capability-summary-item"
          >
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400/80" aria-hidden />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
