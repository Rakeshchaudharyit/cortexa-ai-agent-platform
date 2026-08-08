import Link from "next/link";

import { AgentToolsOverview } from "@/components/AgentToolsOverview";
import { AuthHeader } from "@/components/AuthHeader";
import { CapabilitiesSummary } from "@/components/CapabilitiesSummary";
import { DocumentPanel } from "@/components/documents/DocumentPanel";
import { PlatformCapabilities } from "@/components/PlatformCapabilities";
import { QuickActions } from "@/components/QuickActions";
import { SystemStatusPanel } from "@/components/SystemStatusPanel";

export default function HomePage() {
  return (
    <main id="main-content" tabIndex={-1} className="mx-auto flex min-h-screen w-full max-w-[1240px] flex-col gap-8 px-4 py-5 sm:gap-10 sm:px-8 sm:py-8 lg:px-10 lg:py-10">
      <header className="relative overflow-hidden rounded-3xl border border-white/10 bg-slate-950/40 p-5 shadow-2xl shadow-black/10 backdrop-blur-sm sm:p-8 lg:p-10">
        <div className="pointer-events-none absolute -right-32 -top-32 h-80 w-80 rounded-full bg-cyan-400/10 blur-3xl" />
        <div className="relative">
          <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-cyan-400 text-sm font-black tracking-tight text-slate-950 shadow-lg shadow-cyan-950/30">
                C
              </div>
              <div>
                <p className="text-sm font-semibold text-white">Cortexa</p>
                <p className="text-xs text-slate-500">AI Knowledge Platform</p>
              </div>
            </div>
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/15 bg-emerald-500/[0.07] px-3 py-1.5 text-xs font-medium text-emerald-200" data-testid="platform-status-badge">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              Secure knowledge operations
            </div>
          </div>

          <div className="grid items-end gap-8 lg:grid-cols-[1fr_auto]">
            <div>
              <p className="cx-eyebrow">Enterprise RAG · Knowledge Management · AI Quality</p>
              <h1 className="mt-3 max-w-4xl text-4xl font-semibold tracking-[-0.035em] text-white sm:text-5xl lg:text-[3.5rem] lg:leading-[1.04]">
                Turn private knowledge into grounded, measurable AI answers.
              </h1>
              <p className="mt-5 max-w-3xl text-base leading-7 text-slate-300 sm:text-lg">
                Secure document intelligence with citations, versioned knowledge, automated RAG evaluation,
                human feedback review, enterprise analytics, and durable background processing.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Link href="/chat" className="cx-button-primary">Open knowledge chat</Link>
                <Link href="/admin/analytics" className="cx-button-secondary">View AI quality</Link>
              </div>
            </div>
            <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2 lg:w-auto lg:min-w-[280px]" data-testid="phase-badge">
              <div className="cx-kpi p-4">
                <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">Retrieval</p>
                <p className="mt-2 text-lg font-semibold text-white">Grounded RAG</p>
                <p className="mt-1 text-xs text-slate-500">Citations + quality controls</p>
              </div>
              <div className="cx-kpi p-4">
                <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">Operations</p>
                <p className="mt-2 text-lg font-semibold text-white">Durable Jobs</p>
                <p className="mt-1 text-xs text-slate-500">Redis + PostgreSQL ledger</p>
              </div>
            </div>
          </div>

          <div className="mt-8 border-t border-white/10 pt-4">
            <AuthHeader />
          </div>
        </div>
      </header>

      <QuickActions />
      <PlatformCapabilities />
      <CapabilitiesSummary />
      <AgentToolsOverview />
      <SystemStatusPanel />
      <DocumentPanel />

      <footer className="border-t border-white/10 py-6 text-center text-xs text-slate-600">
        Cortexa AI Knowledge Platform · Enterprise AI engineering portfolio
      </footer>
    </main>
  );
}
