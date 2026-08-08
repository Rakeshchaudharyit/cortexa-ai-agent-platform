"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { EmptyState } from "@/components/admin/EmptyState";
import { MetricCard } from "@/components/admin/MetricCard";
import { fetchAdminAnalytics } from "@/services/admin";
import type { AdminAnalyticsResponse } from "@/types/admin";

const tooltipStyle = {
  background: "#081321",
  border: "1px solid rgba(148,163,184,0.18)",
  borderRadius: 12,
  boxShadow: "0 16px 40px rgba(0,0,0,0.28)",
};

function AnalyticsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 xl:grid-cols-[1.2fr_2fr]">
        <div className="h-52 animate-pulse rounded-3xl bg-white/[0.04]" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-28 animate-pulse rounded-2xl bg-white/[0.04]" />)}</div>
      </div>
      <div className="grid gap-6 xl:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-80 animate-pulse rounded-2xl bg-white/[0.04]" />)}</div>
    </div>
  );
}

function SectionHeader({ eyebrow, title, description, legend }: { eyebrow: string; title: string; description?: string; legend?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="cx-eyebrow">{eyebrow}</p>
        <h2 className="mt-2 text-base font-semibold text-white">{title}</h2>
        {description ? <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p> : null}
      </div>
      {legend}
    </div>
  );
}

function RankedList({ title, eyebrow, items }: { title: string; eyebrow: string; items: Array<{ label: string; value: number; secondary: string | null }> }) {
  const maxValue = Math.max(...items.map((item) => item.value), 1);
  return (
    <section className="cx-panel p-5">
      <SectionHeader eyebrow={eyebrow} title={title} />
      <div className="mt-5 space-y-4">
        {items.length ? items.map((item, index) => (
          <div key={`${item.label}-${index}`}>
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-200">{item.label}</p>
                {item.secondary ? <p className="mt-0.5 truncate text-xs text-slate-600">{item.secondary}</p> : null}
              </div>
              <span className="shrink-0 rounded-lg border border-white/8 bg-white/[0.04] px-2.5 py-1 text-xs font-semibold text-cyan-100">{item.value.toLocaleString()}</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
              <div className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-teal-400" style={{ width: `${Math.max((item.value / maxValue) * 100, 4)}%` }} />
            </div>
          </div>
        )) : <p className="rounded-xl border border-dashed border-white/8 bg-white/[0.02] px-4 py-6 text-center text-sm text-slate-500">No data in this period.</p>}
      </div>
    </section>
  );
}

function QualityBreakdown({ data }: { data: AdminAnalyticsResponse }) {
  const components = [
    { label: "Evaluation", value: data.quality.evaluation_score },
    { label: "Helpful feedback", value: data.quality.feedback_score },
    { label: "Response success", value: data.quality.success_score },
    { label: "Citation coverage", value: data.quality.citation_coverage_score },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {components.map((component) => (
        <div key={component.label} className="rounded-2xl border border-white/8 bg-white/[0.025] p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs font-medium text-slate-400">{component.label}</p>
            <span className="text-sm font-semibold text-white">{component.value == null ? "N/A" : `${component.value}%`}</span>
          </div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
            <div className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-teal-400 transition-all" style={{ width: `${component.value ?? 0}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AdminAnalyticsPage() {
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const [data, setData] = useState<AdminAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      const result = await fetchAdminAnalytics(days);
      if (!cancelled) {
        setData(result.ok ? result.data : null);
        setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [days]);

  const totals = data?.totals;
  const feedbackRate = data?.feedback.helpful_rate == null ? null : Math.round(data.feedback.helpful_rate * 100);
  const knowledgeBars = useMemo(() => data ? [
    { category: "Ready", count: data.knowledge_health.ready_documents },
    { category: "Pending", count: data.knowledge_health.pending_documents },
    { category: "Processing", count: data.knowledge_health.processing_documents },
    { category: "Failed", count: data.knowledge_health.failed_documents },
    { category: "No chunks", count: data.knowledge_health.zero_chunk_documents },
    { category: "Stale", count: data.knowledge_health.stale_documents },
  ] : [], [data]);

  return (
    <div data-testid="admin-analytics-page">
      <AdminPageHeader
        title="Enterprise AI Analytics"
        description="Measure answer quality, knowledge readiness, user feedback, model usage, and response performance without exposing private content."
        actions={
          <div className="flex rounded-xl border border-white/8 bg-black/15 p-1" data-testid="admin-analytics-range">
            {[7, 30, 90].map((value) => (
              <button
                key={value}
                type="button"
                className={`min-w-12 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${days === value ? "bg-cyan-400 text-slate-950 shadow-sm" : "text-slate-400 hover:bg-white/[0.05] hover:text-white"}`}
                onClick={() => setDays(value as 7 | 30 | 90)}
              >
                {value}d
              </button>
            ))}
          </div>
        }
      />

      {loading ? <AnalyticsSkeleton /> : !data ? <EmptyState title="Analytics unavailable" description="Operational analytics will appear when AI activity is available." /> : (
        <>
          <section className="mb-6 grid gap-4 xl:grid-cols-[1.15fr_2fr]">
            <div className="relative overflow-hidden rounded-3xl border border-cyan-400/20 bg-gradient-to-br from-cyan-400/[0.14] via-slate-950/70 to-indigo-500/[0.10] p-6 shadow-[0_24px_80px_rgba(0,0,0,0.24)]">
              <div className="absolute -right-24 -top-24 h-64 w-64 rounded-full bg-cyan-400/10 blur-3xl" />
              <div className="relative">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="cx-eyebrow">AI quality score</p>
                    <div className="mt-4 flex items-end gap-3">
                      <span className="text-5xl font-semibold tracking-tight text-white sm:text-6xl">{data.quality.score ?? "N/A"}</span>
                      {data.quality.score != null ? <span className="pb-1.5 text-lg text-slate-400">/ 100</span> : null}
                    </div>
                  </div>
                  <span className="rounded-full border border-cyan-300/15 bg-cyan-300/[0.06] px-3 py-1.5 text-xs font-semibold text-cyan-100">{data.quality.label}</span>
                </div>
                <p className="mt-4 max-w-lg text-xs leading-5 text-slate-400">A normalized operational signal built from evaluation performance, human feedback, response reliability, and citation coverage. Missing inputs are excluded rather than scored as zero.</p>
                <div className="mt-5 grid grid-cols-2 gap-3 text-xs">
                  <div className="rounded-xl border border-white/8 bg-black/10 p-3"><span className="text-slate-500">Knowledge health</span><p className="mt-1 text-base font-semibold text-white">{data.knowledge_health.health_score ?? "N/A"}%</p></div>
                  <div className="rounded-xl border border-white/8 bg-black/10 p-3"><span className="text-slate-500">Helpful rate</span><p className="mt-1 text-base font-semibold text-white">{feedbackRate ?? "N/A"}%</p></div>
                </div>
              </div>
            </div>
            <QualityBreakdown data={data} />
          </section>

          <section className="mb-6">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <p className="cx-eyebrow">Operational snapshot</p>
                <h2 className="mt-2 text-base font-semibold text-white">AI delivery metrics</h2>
              </div>
              <p className="hidden text-xs text-slate-600 sm:block">Last {days} days</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard label="AI responses" value={Number(totals?.successful_responses || 0) + Number(totals?.failed_responses || 0)} />
              <MetricCard label="Average response" value={totals?.ai_latency_ms == null ? null : Math.round(Number(totals.ai_latency_ms))} unit="ms" hint="End-to-end latency" />
              <MetricCard label="RAG queries" value={Number(totals?.rag_queries || 0)} />
              <MetricCard label="No-answer responses" value={Number(totals?.no_answer_responses || 0)} hint="Safe unavailable-information responses" />
              <MetricCard label="Helpful rate" value={feedbackRate} unit="%" hint={`${data.feedback.total} feedback items`} />
              <MetricCard label="Open reviews" value={data.feedback.open_reviews} hint="Human quality review queue" />
              <MetricCard label="Knowledge health" value={data.knowledge_health.health_score} unit="%" />
              <MetricCard label="Known tokens" value={Number(totals?.total_tokens || 0)} />
            </div>
          </section>

          <div className="mb-6 grid gap-6 xl:grid-cols-2">
            <section className="cx-panel p-5">
              <SectionHeader
                eyebrow="Reliability"
                title="AI request outcomes"
                description="Successful, failed, and safe no-answer responses over time."
                legend={<div className="flex flex-wrap gap-3 text-[11px] text-slate-500"><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-teal-400" />Successful</span><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-rose-400" />Failed</span><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-amber-300" />No answer</span></div>}
              />
              <div className="mt-5 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.points} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
                    <XAxis dataKey="date" axisLine={false} tickLine={false} stroke="#64748b" tick={{ fontSize: 10 }} />
                    <YAxis axisLine={false} tickLine={false} stroke="#64748b" tick={{ fontSize: 10 }} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Line type="monotone" dataKey="successful_responses" stroke="#2dd4bf" strokeWidth={2} dot={false} name="Successful" />
                    <Line type="monotone" dataKey="failed_responses" stroke="#fb7185" strokeWidth={1.5} dot={false} name="Failed" />
                    <Line type="monotone" dataKey="no_answer_responses" stroke="#fbbf24" strokeWidth={1.5} dot={false} name="No answer" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section className="cx-panel p-5">
              <SectionHeader
                eyebrow="Performance"
                title="Latency by day"
                description="End-to-end response, retrieval, and model generation latency."
                legend={<div className="flex flex-wrap gap-3 text-[11px] text-slate-500"><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-cyan-400" />Response</span><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-indigo-400" />Retrieval</span><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-violet-400" />Generation</span></div>}
              />
              <div className="mt-5 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.points} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                    <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
                    <XAxis dataKey="date" axisLine={false} tickLine={false} stroke="#64748b" tick={{ fontSize: 10 }} />
                    <YAxis axisLine={false} tickLine={false} stroke="#64748b" tick={{ fontSize: 10 }} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Line type="monotone" dataKey="ai_latency_ms" stroke="#22d3ee" strokeWidth={2} dot={false} name="Response" />
                    <Line type="monotone" dataKey="retrieval_latency_ms" stroke="#818cf8" strokeWidth={1.5} dot={false} name="Retrieval" />
                    <Line type="monotone" dataKey="generation_latency_ms" stroke="#a78bfa" strokeWidth={1.5} dot={false} name="Generation" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section className="cx-panel p-5">
              <SectionHeader eyebrow="Knowledge quality" title="Knowledge health" description="Documents requiring operational attention across the knowledge base." />
              <div className="mt-5 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={knowledgeBars} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
                    <XAxis dataKey="category" axisLine={false} tickLine={false} stroke="#64748b" tick={{ fontSize: 10 }} />
                    <YAxis axisLine={false} tickLine={false} stroke="#64748b" allowDecimals={false} tick={{ fontSize: 10 }} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Bar dataKey="count" fill="#22d3ee" radius={[8, 8, 2, 2]} maxBarSize={58} name="Documents" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section className="cx-panel p-5">
              <SectionHeader eyebrow="Regression quality" title="Evaluation trend" description="Average evaluation score and pass rate for completed RAG test runs." />
              {data.evaluation_trend.length ? (
                <div className="mt-5 h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data.evaluation_trend} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                      <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
                      <XAxis dataKey="date" axisLine={false} tickLine={false} stroke="#64748b" tick={{ fontSize: 10 }} />
                      <YAxis domain={[0,100]} axisLine={false} tickLine={false} stroke="#64748b" tick={{ fontSize: 10 }} />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Line type="monotone" dataKey="average_score" stroke="#2dd4bf" strokeWidth={2} dot={{ r: 2 }} name="Average score" />
                      <Line type="monotone" dataKey="pass_rate" stroke="#818cf8" strokeWidth={1.5} dot={false} name="Pass rate" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : <div className="mt-5 flex h-72 items-center justify-center rounded-2xl border border-dashed border-white/8 bg-white/[0.015] px-6 text-center text-sm text-slate-500">Run RAG evaluations to build a measurable quality trend.</div>}
            </section>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <RankedList eyebrow="Knowledge usage" title="Most-used knowledge documents" items={data.top_documents} />
            <RankedList eyebrow="AI runtime" title="Model usage" items={data.top_models} />
          </div>

          <section className="mt-6 cx-panel p-5">
            <SectionHeader eyebrow="Knowledge operations" title="Health details" description="Actionable quality signals for document readiness and freshness." />
            <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <MetricCard label="Total documents" value={data.knowledge_health.total_documents} />
              <MetricCard label="Failed" value={data.knowledge_health.failed_documents} hint="Requires ingestion review" />
              <MetricCard label="Without chunks" value={data.knowledge_health.zero_chunk_documents} hint="Unavailable for retrieval" />
              <MetricCard label="Stale over 90d" value={data.knowledge_health.stale_documents} hint="Review for freshness" />
            </div>
            {data.knowledge_health.duplicate_content_groups > 0 ? <div className="mt-4 rounded-xl border border-amber-300/15 bg-amber-300/[0.05] px-4 py-3 text-xs text-amber-100">{data.knowledge_health.duplicate_content_groups} duplicate content group{data.knowledge_health.duplicate_content_groups === 1 ? "" : "s"} detected. Review knowledge inventory to reduce retrieval noise.</div> : null}
          </section>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-white/5 pt-4 text-xs text-slate-600">
            <p>Privacy by design: analytics exclude prompts, answers, retrieved passages, memory content, and hidden reasoning.</p>
            <p>Updated {new Date(data.generated_at).toLocaleString()}</p>
          </div>
        </>
      )}
    </div>
  );
}
