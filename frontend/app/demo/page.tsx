import Link from "next/link";
import { PublicFooter } from "@/components/public/PublicFooter";
import { PublicHeader } from "@/components/public/PublicHeader";

const tour = [
  ["01", "Grounded knowledge chat", "Upload private knowledge, ask questions in Document Knowledge mode, and inspect source citations attached to the answer.", "/login", "Open live workspace"],
  ["02", "Knowledge governance", "Organize sources, track immutable versions, select the active RAG version, archive or restore knowledge, and inspect lifecycle history.", "/login", "Explore knowledge"],
  ["03", "RAG quality evaluation", "Create repeatable evaluation cases, run them in background workers, compare quality metrics, and export results for review.", "/login", "Open evaluations"],
  ["04", "Human feedback review", "Collect helpful/not-helpful ratings, classify issues, add admin review notes, and resolve quality feedback in a governed workflow.", "/login", "Review feedback"],
  ["05", "Enterprise analytics", "Monitor AI quality, success rate, latency, citations, feedback, knowledge health, evaluation trends, document usage, and model usage.", "/login", "View analytics"],
  ["06", "Background operations", "Observe durable ingestion and evaluation jobs, progress, cancellation, retries, queue health, dead-letter handling, and safe requeue operations.", "/login", "Open operations"],
] as const;

export default function DemoPage() {
  return (
    <div className="min-h-screen bg-[#050b13] text-slate-100">
      <PublicHeader />
      <main id="main-content" tabIndex={-1}>
        <section className="mx-auto w-full max-w-[1100px] px-4 py-16 sm:px-8 sm:py-20 lg:px-10">
          <div className="max-w-3xl"><p className="cx-eyebrow">Guided product tour</p><h1 className="mt-3 text-4xl font-semibold tracking-[-0.035em] text-white sm:text-5xl">See what the platform demonstrates.</h1><p className="mt-5 text-base leading-7 text-slate-400">This tour describes implemented product workflows. It intentionally avoids synthetic performance numbers or fabricated customer data. Sign in to exercise the live functionality.</p></div>

          <div className="mt-10 grid gap-4 md:grid-cols-2">
            {tour.map(([num,title,body,href,cta]) => (
              <article key={num} className="cx-panel flex flex-col p-6">
                <div className="flex items-center justify-between"><span className="text-xs font-semibold tracking-[0.18em] text-cyan-300/75">{num}</span><span className="rounded-full border border-emerald-400/15 bg-emerald-500/[0.055] px-2.5 py-1 text-[10px] font-medium text-emerald-200">Implemented</span></div>
                <h2 className="mt-5 text-xl font-semibold text-white">{title}</h2>
                <p className="mt-3 flex-1 text-sm leading-6 text-slate-400">{body}</p>
                <Link href={href} className="mt-6 inline-flex text-sm font-semibold text-cyan-300 transition hover:text-cyan-200">{cta} →</Link>
              </article>
            ))}
          </div>

          <section className="mt-10 cx-panel p-7">
            <div className="grid gap-8 lg:grid-cols-[.8fr_1.2fr]">
              <div><p className="cx-eyebrow">Demo knowledge pack</p><h2 className="mt-3 text-2xl font-semibold text-white">A repeatable browser demo without fake business data.</h2><p className="mt-3 text-sm leading-6 text-slate-400">The repository includes sample architecture, operations, security, and product-governance documents under <code className="rounded bg-white/[0.05] px-1.5 py-0.5 text-cyan-200">demo/knowledge</code>.</p></div>
              <div className="grid gap-3 sm:grid-cols-2">{["Platform Architecture","Deployment & Operations","Security & Access Policy","AI Quality & Governance"].map((x) => <div key={x} className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm font-medium text-slate-200">{x}</div>)}</div>
            </div>
          </section>

          <section className="mt-10 rounded-3xl border border-cyan-400/15 bg-cyan-400/[0.035] p-7 text-center sm:p-10"><p className="cx-eyebrow">Live workspace</p><h2 className="mt-3 text-3xl font-semibold text-white">Ready to test the real flows?</h2><p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-slate-400">Use the live workspace to upload the bundled demo knowledge, run grounded questions, inspect citations, execute evaluations, submit feedback, and monitor background jobs.</p><div className="mt-6 flex justify-center gap-3"><Link href="/login" className="cx-button-primary">Sign in to workspace</Link><Link href="/" className="cx-button-secondary">Back to overview</Link></div></section>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
