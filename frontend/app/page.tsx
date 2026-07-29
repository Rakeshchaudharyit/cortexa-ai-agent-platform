import { AuthHeader } from "@/components/AuthHeader";
import { SystemStatusPanel } from "@/components/SystemStatusPanel";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-10 px-6 py-12 sm:px-10">
      <header className="flex flex-col gap-4 border-b border-white/10 pb-8">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-300/90">
          Phase 3 — Authentication
        </p>
        <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-slate-50 sm:text-5xl">
          Cortexa AI Agent Platform
        </h1>
        <p className="max-w-2xl text-base leading-relaxed text-slate-300 sm:text-lg">
          Local-first foundation with authentication, secure refresh sessions, and an Ollama
          LLM provider. Generation endpoints require a signed-in user.
        </p>
        <p
          className="inline-flex w-fit items-center rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-medium text-cyan-200 ring-1 ring-cyan-400/20"
          data-testid="phase-badge"
        >
          Phase 3 status: Authentication online
        </p>
        <AuthHeader />
      </header>

      <SystemStatusPanel />
    </main>
  );
}
