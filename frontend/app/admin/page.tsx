"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ActivityTimeline } from "@/components/admin/ActivityTimeline";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { EmptyState } from "@/components/admin/EmptyState";
import { MetricCard } from "@/components/admin/MetricCard";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { fetchAdminAnalytics, fetchAdminDashboard } from "@/services/admin";
import type { AdminAnalyticsResponse, AdminDashboardResponse } from "@/types/admin";

const chartTooltipStyle = {
  background: "#081321",
  border: "1px solid rgba(148,163,184,0.18)",
  borderRadius: 12,
  boxShadow: "0 16px 40px rgba(0,0,0,0.28)",
};

function DashboardSkeleton() {
  return (
    <div className="space-y-6" data-testid="admin-dashboard-loading">
      <div className="h-44 animate-pulse rounded-3xl bg-white/[0.04]" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-28 animate-pulse rounded-2xl bg-white/[0.04]" />
        ))}
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="h-80 animate-pulse rounded-2xl bg-white/[0.04]" />
        <div className="h-80 animate-pulse rounded-2xl bg-white/[0.04]" />
      </div>
    </div>
  );
}

function QuickLink({ href, title, description, eyebrow }: { href: string; title: string; description: string; eyebrow: string }) {
  return (
    <Link
      href={href}
      className="group rounded-2xl border border-white/8 bg-white/[0.025] p-4 transition hover:-translate-y-0.5 hover:border-cyan-400/25 hover:bg-cyan-400/[0.045]"
    >
      <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-300/70">{eyebrow}</p>
      <div className="mt-2 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
        </div>
        <span className="mt-0.5 text-lg text-slate-600 transition group-hover:translate-x-0.5 group-hover:text-cyan-300">→</span>
      </div>
    </Link>
  );
}

function SystemHealth({ data }: { data: AdminDashboardResponse }) {
  const services = Object.entries({
    backend: data.system_status.backend,
    postgres: data.system_status.postgres,
    redis: data.system_status.redis,
    ollama: data.system_status.ollama,
    storage: data.system_status.storage,
  });

  return (
    <section className="cx-panel p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="cx-eyebrow">Operations</p>
          <h3 className="mt-2 text-base font-semibold text-white">System health</h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">Live service readiness across the AI stack.</p>
        </div>
        <Link href="/admin/system" className="text-xs font-medium text-cyan-300 transition hover:text-cyan-200">View system →</Link>
      </div>
      <div className="mt-5 divide-y divide-white/5">
        {services.map(([name, status]) => (
          <div key={name} className="flex items-center justify-between py-2.5 first:pt-0 last:pb-0">
            <span className="text-sm capitalize text-slate-300">{name}</span>
            <StatusBadge status={status} />
          </div>
        ))}
      </div>
      <div className="mt-4 rounded-xl border border-white/5 bg-white/[0.025] px-3 py-2.5 text-xs text-slate-500">
        Model: <span className="font-medium text-slate-300">{data.ai_activity.model}</span>
        <span className="mx-2 text-slate-700">•</span>
        Provider: <span className="font-medium text-slate-300">{data.ai_activity.provider}</span>
      </div>
    </section>
  );
}

export default function AdminDashboardPage() {
  const [data, setData] = useState<AdminDashboardResponse | null>(null);
  const [analytics, setAnalytics] = useState<AdminAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      const [dashboardResult, analyticsResult] = await Promise.all([
        fetchAdminDashboard(),
        fetchAdminAnalytics(30),
      ]);
      if (cancelled) return;

      if (!dashboardResult.ok) {
        setError(dashboardResult.error);
        setData(null);
      } else {
        setData(dashboardResult.data);
        setError(null);
      }
      setAnalytics(analyticsResult.ok ? analyticsResult.data : null);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const metricMap = useMemo(
    () => new Map(data?.metrics.map((metric) => [metric.key, metric]) ?? []),
    [data],
  );

  if (loading) return <DashboardSkeleton />;
  if (error) return <EmptyState title="Unable to load dashboard" description={error} />;
  if (!data) return <EmptyState title="No dashboard data" description="Metrics will appear once the platform is in use." />;

  const qualityScore = analytics?.quality.score ?? null;
  const helpfulRate = analytics?.feedback.helpful_rate == null ? null : Math.round(analytics.feedback.helpful_rate * 100);
  const responseSuccess = analytics?.quality.success_score ?? null;
  const averageResponse = analytics?.totals.ai_latency_ms == null ? metricMap.get("average_response_time_ms")?.value ?? null : Math.round(Number(analytics.totals.ai_latency_ms));
  const readyDocuments = metricMap.get("documents_ready")?.value ?? 0;
  const totalDocuments = metricMap.get("documents_total")?.value ?? 0;
  const readyRate = totalDocuments ? Math.round((Number(readyDocuments) / Number(totalDocuments)) * 100) : null;

  return (
    <div data-testid="admin-dashboard">
      <AdminPageHeader
        title="AI operations overview"
        description="A concise view of answer quality, knowledge readiness, platform usage, and operational health."
        actions={
          <div className="flex gap-2">
            <Link href="/admin/analytics" className="cx-button-secondary">View analytics</Link>
            <Link href="/admin/evaluations" className="cx-button-primary">Run evaluation</Link>
          </div>
        }
      />

      <section className="mb-6 grid gap-4 xl:grid-cols-[1.35fr_2fr]">
        <div className="relative overflow-hidden rounded-3xl border border-cyan-400/20 bg-gradient-to-br from-cyan-400/[0.13] via-slate-950/60 to-indigo-500/[0.10] p-6 shadow-[0_24px_80px_rgba(0,0,0,0.24)]">
          <div className="absolute -right-20 -top-20 h-56 w-56 rounded-full bg-cyan-400/10 blur-3xl" />
          <div className="relative">
            <div className="flex items-center justify-between gap-4">
              <p className="cx-eyebrow">AI quality</p>
              <span className="rounded-full border border-white/10 bg-black/15 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.16em] text-slate-400">30-day signal</span>
            </div>
            <div className="mt-5 flex items-end gap-3">
              <span className="text-5xl font-semibold tracking-tight text-white sm:text-6xl">{qualityScore ?? "N/A"}</span>
              {qualityScore != null ? <span className="pb-1.5 text-lg text-slate-400">/ 100</span> : null}
            </div>
            <p className="mt-2 text-sm font-medium text-cyan-100">{analytics?.quality.label ?? "Build evaluation and feedback history to calculate quality."}</p>
            <p className="mt-4 max-w-xl text-xs leading-5 text-slate-400">Composite operational signal from evaluation quality, user feedback, response reliability, and citation coverage.</p>
            <div className="mt-5 flex flex-wrap gap-2 text-xs">
              <span className="rounded-full border border-white/8 bg-white/[0.04] px-3 py-1.5 text-slate-300">Knowledge health {analytics?.knowledge_health.health_score ?? "N/A"}%</span>
              <span className="rounded-full border border-white/8 bg-white/[0.04] px-3 py-1.5 text-slate-300">Helpful {helpfulRate ?? "N/A"}%</span>
              <span className="rounded-full border border-white/8 bg-white/[0.04] px-3 py-1.5 text-slate-300">Success {responseSuccess ?? "N/A"}%</span>
            </div>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Knowledge ready" value={readyRate} unit="%" hint={`${Number(readyDocuments).toLocaleString()} of ${Number(totalDocuments).toLocaleString()} documents`} />
          <MetricCard label="Avg response" value={averageResponse} unit="ms" hint="End-to-end AI latency" />
          <MetricCard label="Conversations" value={metricMap.get("conversations_total")?.value ?? null} />
          <MetricCard label="Messages · 24h" value={metricMap.get("messages_24h")?.value ?? null} />
          <MetricCard label="RAG queries · 30d" value={analytics ? Number(analytics.totals.rag_queries || 0) : null} unavailable={!analytics} />
          <MetricCard label="Helpful feedback" value={helpfulRate} unit="%" unavailable={!analytics || helpfulRate == null} />
          <MetricCard label="Active users" value={metricMap.get("users_active")?.value ?? null} />
          <MetricCard label="Failed AI requests" value={metricMap.get("failed_ai_requests")?.value ?? null} />
        </div>
      </section>

      <section className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <QuickLink href="/admin/documents" eyebrow="Knowledge" title="Manage knowledge" description="Review ingestion, lifecycle, versions, and document readiness." />
        <QuickLink href="/admin/evaluations" eyebrow="AI quality" title="Run RAG evaluation" description="Measure groundedness, citations, answerability, and regression quality." />
        <QuickLink href="/admin/feedback" eyebrow="Human review" title="Review feedback" description="Resolve reported answers and capture quality improvement signals." />
        <QuickLink href="/admin/jobs" eyebrow="Operations" title="Monitor background work" description="Inspect durable jobs, retries, queue pressure, and worker health." />
      </section>

      <div className="mb-6 grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <section className="cx-panel p-5" data-testid="admin-usage-trend">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="cx-eyebrow">Platform activity</p>
              <h3 className="mt-2 text-base font-semibold text-white">Usage trend</h3>
              <p className="mt-1 text-xs text-slate-500">Conversation, message, and tool activity across the last two weeks.</p>
            </div>
            <div className="flex flex-wrap gap-3 text-[11px] text-slate-500">
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-cyan-400" />Messages</span>
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-teal-400" />Conversations</span>
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-indigo-400" />Tools</span>
            </div>
          </div>
          {data.usage_trend.length ? (
            <div className="mt-5 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.usage_trend} margin={{ top: 8, right: 6, left: -14, bottom: 0 }}>
                  <defs>
                    <linearGradient id="messagesFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#22d3ee" stopOpacity={0.22} /><stop offset="100%" stopColor="#22d3ee" stopOpacity={0} /></linearGradient>
                    <linearGradient id="conversationsFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2dd4bf" stopOpacity={0.15} /><stop offset="100%" stopColor="#2dd4bf" stopOpacity={0} /></linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
                  <XAxis dataKey="date" axisLine={false} tickLine={false} stroke="#64748b" tick={{ fontSize: 10 }} />
                  <YAxis axisLine={false} tickLine={false} stroke="#64748b" tick={{ fontSize: 10 }} />
                  <Tooltip contentStyle={chartTooltipStyle} />
                  <Area type="monotone" dataKey="messages" stroke="#22d3ee" strokeWidth={2} fill="url(#messagesFill)" name="Messages" />
                  <Area type="monotone" dataKey="conversations" stroke="#2dd4bf" strokeWidth={1.5} fill="url(#conversationsFill)" name="Conversations" />
                  <Area type="monotone" dataKey="tool_executions" stroke="#818cf8" strokeWidth={1.5} fill="transparent" name="Tools" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : <div className="mt-5"><EmptyState title="No usage yet" description="Activity trends will appear as users interact with the platform." /></div>}
        </section>

        <SystemHealth data={data} />
      </div>

      <div className="mb-6 grid gap-6 xl:grid-cols-[1fr_1fr]">
        <section className="cx-panel p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="cx-eyebrow">Knowledge pipeline</p>
              <h3 className="mt-2 text-base font-semibold text-white">Document readiness</h3>
              <p className="mt-1 text-xs text-slate-500">Current ingestion status across the knowledge base.</p>
            </div>
            <Link href="/admin/documents" className="text-xs font-medium text-cyan-300 transition hover:text-cyan-200">View documents →</Link>
          </div>
          <div className="mt-5 h-60">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.document_pipeline} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
                <XAxis dataKey="status" axisLine={false} tickLine={false} stroke="#64748b" tick={{ fontSize: 10 }} />
                <YAxis axisLine={false} tickLine={false} stroke="#64748b" tick={{ fontSize: 10 }} allowDecimals={false} />
                <Tooltip contentStyle={chartTooltipStyle} />
                <Bar dataKey="count" fill="#22d3ee" radius={[8, 8, 2, 2]} maxBarSize={72} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="cx-panel p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="cx-eyebrow">Audit trail</p>
              <h3 className="mt-2 text-base font-semibold text-white">Recent platform activity</h3>
              <p className="mt-1 text-xs text-slate-500">Latest operational and administrative changes.</p>
            </div>
            <Link href="/admin/audit" className="text-xs font-medium text-cyan-300 transition hover:text-cyan-200">View audit →</Link>
          </div>
          <div className="mt-4 max-h-64 overflow-y-auto pr-1">
            <ActivityTimeline items={data.recent_activity.slice(0, 7)} />
          </div>
        </section>
      </div>

      <p className="text-xs text-slate-600">Updated {new Date(data.generated_at).toLocaleString()} · Operational metrics only; no prompts, private document passages, or hidden reasoning are exposed.</p>
    </div>
  );
}
