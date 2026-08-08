const BUILTIN_TOOLS = [
  {
    name: "Calculator",
    description:
      "Safely evaluates arithmetic expressions without eval or arbitrary code execution.",
  },
  {
    name: "Current Date & Time",
    description: "Returns timezone-aware date and time using valid IANA timezone names.",
  },
  {
    name: "Knowledge Search",
    description:
      "Searches only the authenticated user's authorized documents and preserves citations.",
  },
  {
    name: "Conversation Summary",
    description: "Summarizes owned conversations with message and token limits.",
  },
] as const;

export function AgentToolsOverview() {
  return (
    <section className="flex flex-col gap-4" data-testid="agent-tools-overview" id="agent-tools">
      <div>
        <h2 className="text-lg font-semibold text-slate-100">Built-in AI Tools</h2>
        <p className="mt-1 text-sm text-slate-400">
          Approved, server-validated tools available to the general assistant when a task requires structured execution.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {BUILTIN_TOOLS.map((tool) => (
          <article
            key={tool.name}
            className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3"
            data-testid="builtin-tool-card"
          >
            <h3 className="text-sm font-semibold text-slate-100">{tool.name}</h3>
            <p className="mt-1 text-sm leading-relaxed text-slate-400">{tool.description}</p>
          </article>
        ))}
      </div>
      <p
        className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100/90"
        data-testid="agent-tools-security-note"
      >
        All tool names and arguments are validated server-side. The platform does not allow
        arbitrary shell, SQL, Python, or file-system execution.
      </p>
    </section>
  );
}
