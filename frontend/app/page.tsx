import Link from "next/link";

import { PublicFooter } from "@/components/public/PublicFooter";
import { PublicHeader } from "@/components/public/PublicHeader";

const capabilities = [
  ["Grounded RAG", "Ask questions across private documents with pgvector retrieval, bounded context, citation validation, and safe no-answer behavior."],
  ["Knowledge lifecycle", "Organize sources into folders, maintain immutable versions, activate or restore versions, archive knowledge, and audit lifecycle events."],
  ["Automated evaluation", "Run repeatable RAG quality cases in background workers and track groundedness, citation match, expected-answer quality, and pass rates."],
  ["Human feedback", "Capture helpful or not-helpful ratings, structured issue reasons, and a review workflow for AI quality operations."],
  ["Enterprise analytics", "Measure quality, response reliability, latency, knowledge health, document usage, model usage, feedback, and evaluation trends."],
  ["Durable operations", "Redis-backed delivery with a PostgreSQL job ledger, retries, cancellation, dead-letter handling, worker health, and background ingestion."],
] as const;

const stack = ["Next.js", "TypeScript", "FastAPI", "Python", "PostgreSQL", "pgvector", "Redis", "Ollama", "Docker"];

export default function PublicLandingPage() {
  return (
    <div className="min-h-screen bg-[#050b13] text-slate-100">
      <PublicHeader />
      <main id="main-content" tabIndex={-1}>
        <section className="relative overflow-hidden border-b border-white/10">
          <div className="pointer-events-none absolute left-1/2 top-[-180px] h-[520px] w-[900px] -translate-x-1/2 rounded-full bg-cyan-400/[0.08] blur-3xl" />
          <div className="relative mx-auto grid w-full max-w-[1240px] gap-12 px-4 py-20 sm:px-8 sm:py-28 lg:grid-cols-[1.06fr_.94fr] lg:items-center lg:px-10 lg:py-32">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/15 bg-cyan-400/[0.055] px-3 py-1.5 text-xs font-semibold text-cyan-200">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                Production-oriented enterprise AI portfolio
              </div>
              <p className="mt-7 cx-eyebrow">Enterprise RAG · Knowledge Management · AI Quality</p>
              <h1 className="mt-4 max-w-4xl text-5xl font-semibold tracking-[-0.045em] text-white sm:text-6xl lg:text-[4.4rem] lg:leading-[1.01]">
                Private knowledge.<br />Grounded answers.<br /><span className="text-cyan-300">Measurable AI quality.</span>
              </h1>
              <p className="mt-7 max-w-2xl text-base leading-7 text-slate-300 sm:text-lg">
                Cortexa is a production-oriented AI knowledge platform built to demonstrate secure RAG, governed document operations, automated evaluations, human quality review, enterprise analytics, and durable background processing.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link href="/demo" className="cx-button-primary">Explore product tour</Link>
                <Link href="/login" className="cx-button-secondary">Open live workspace</Link>
              </div>
              <div className="mt-8 flex flex-wrap gap-2">
                {stack.map((item) => <span key={item} className="rounded-full border border-white/10 bg-white/[0.035] px-3 py-1.5 text-xs text-slate-400">{item}</span>)}
              </div>
            </div>

            <div className="cx-panel overflow-hidden p-3 shadow-2xl shadow-black/25">
              <div className="rounded-2xl border border-white/10 bg-[#07111d] p-5">
                <div className="flex items-center justify-between gap-3 border-b border-white/10 pb-4">
                  <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-300/80">AI quality operations</p><p className="mt-1 text-lg font-semibold text-white">Enterprise control plane</p></div>
                  <span className="rounded-full border border-emerald-400/15 bg-emerald-500/[0.07] px-2.5 py-1 text-[11px] font-medium text-emerald-200">Operational</span>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  {[["RAG answers", "Citations + controls"], ["Knowledge", "Versions + lifecycle"], ["Evaluation", "Regression testing"], ["Workers", "Durable background jobs"]].map(([a,b]) => (
                    <div key={a} className="rounded-xl border border-white/10 bg-white/[0.035] p-4"><p className="text-[10px] uppercase tracking-wider text-slate-500">{a}</p><p className="mt-2 text-sm font-semibold text-white">{b}</p></div>
                  ))}
                </div>
                <div className="mt-3 rounded-xl border border-cyan-400/15 bg-cyan-400/[0.035] p-4">
                  <div className="flex items-center gap-3"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-400/10 text-cyan-300">✓</span><div><p className="text-sm font-medium text-slate-100">Quality is part of the architecture</p><p className="mt-1 text-xs leading-5 text-slate-500">Evaluation, observability, feedback, retrieval controls, and operations are first-class product workflows.</p></div></div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="capabilities" className="mx-auto w-full max-w-[1240px] px-4 py-20 sm:px-8 lg:px-10">
          <div className="max-w-3xl"><p className="cx-eyebrow">Platform capabilities</p><h2 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">Built beyond the chatbot demo.</h2><p className="mt-4 text-base leading-7 text-slate-400">The portfolio focuses on the engineering systems required to make private knowledge useful, governable, measurable, and operable.</p></div>
          <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {capabilities.map(([title, body], i) => (
              <article key={title} className="cx-panel p-6"><div className="flex h-9 w-9 items-center justify-center rounded-xl border border-cyan-400/15 bg-cyan-400/[0.055] text-xs font-bold text-cyan-200">0{i+1}</div><h3 className="mt-5 text-lg font-semibold text-white">{title}</h3><p className="mt-2 text-sm leading-6 text-slate-400">{body}</p></article>
            ))}
          </div>
        </section>

        <section id="architecture" className="border-y border-white/10 bg-white/[0.018]">
          <div className="mx-auto w-full max-w-[1240px] px-4 py-20 sm:px-8 lg:px-10">
            <div className="grid gap-10 lg:grid-cols-[.8fr_1.2fr] lg:items-center">
              <div><p className="cx-eyebrow">Architecture</p><h2 className="mt-3 text-3xl font-semibold tracking-tight text-white">Clear service boundaries. Durable state. Local-first AI.</h2><p className="mt-4 text-sm leading-7 text-slate-400">The platform separates browser experience, typed APIs, application services, durable relational state, queue transport, vector retrieval, and model providers so individual subsystems can evolve independently.</p></div>
              <div className="grid gap-3 sm:grid-cols-5">
                {["Next.js\nFrontend","FastAPI\nAPI","PostgreSQL\n+ pgvector","Redis\nQueue","Ollama\nLLM + embeddings"].map((item, i) => (
                  <div key={item} className="relative rounded-2xl border border-white/10 bg-slate-950/45 p-4 text-center"><p className="whitespace-pre-line text-sm font-semibold text-slate-100">{item}</p>{i < 4 ? <span className="absolute -right-2.5 top-1/2 hidden -translate-y-1/2 text-cyan-400/50 sm:block">→</span> : null}</div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="quality" className="mx-auto w-full max-w-[1240px] px-4 py-20 sm:px-8 lg:px-10">
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="cx-panel p-7"><p className="cx-eyebrow">AI quality loop</p><h2 className="mt-3 text-2xl font-semibold text-white">Evaluate → observe → review → improve.</h2><div className="mt-6 space-y-3">{["Reusable RAG regression cases","Groundedness and citation checks","User helpful/not-helpful feedback","Admin review and resolution workflow","Quality and latency analytics"].map((x) => <div key={x} className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-slate-300"><span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />{x}</div>)}</div></div>
            <div className="cx-panel p-7"><p className="cx-eyebrow">Operational reliability</p><h2 className="mt-3 text-2xl font-semibold text-white">Long-running AI work belongs in workers.</h2><p className="mt-4 text-sm leading-6 text-slate-400">Document ingestion, re-indexing, evaluation runs, and exports use durable background jobs instead of tying execution to browser requests.</p><div className="mt-6 grid grid-cols-2 gap-3">{[["Delivery","Redis"],["Ledger","PostgreSQL"],["Recovery","Retries + dead letter"],["Control","Cancel + requeue"]].map(([a,b]) => <div key={a} className="rounded-xl border border-white/10 bg-white/[0.03] p-4"><p className="text-[10px] uppercase tracking-wider text-slate-500">{a}</p><p className="mt-2 text-sm font-semibold text-white">{b}</p></div>)}</div></div>
          </div>
        </section>

        <section className="border-y border-white/10 bg-cyan-400/[0.025]">
          <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-6 px-4 py-14 sm:px-8 md:flex-row md:items-center md:justify-between lg:px-10">
            <div><p className="text-2xl font-semibold text-white">Explore the product before signing in.</p><p className="mt-2 text-sm text-slate-400">The guided tour explains the implemented workflows and what to test in the live workspace.</p></div>
            <div className="flex flex-wrap gap-3"><Link href="/demo" className="cx-button-primary">View product tour</Link><Link href="/login" className="cx-button-secondary">Sign in</Link></div>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
