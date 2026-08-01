"use client";

import { useEffect, useState } from "react";
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
import { fetchAdminDashboard } from "@/services/admin";
import type { AdminDashboardResponse } from "@/types/admin";

export default function AdminDashboardPage() {
  const [data, setData] = useState<AdminDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      const result = await fetchAdminDashboard();
      if (cancelled) return;
      if (!result.ok) {
        setError(result.error);
        setData(null);
      } else {
        setData(result.data);
        setError(null);
      }
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="admin-dashboard-loading">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-2xl bg-slate-800/40" />
        ))}
      </div>
    );
  }

  if (error) {
    return <EmptyState title="Unable to load dashboard" description={error} />;
  }

  if (!data) {
    return <EmptyState title="No dashboard data" description="Metrics will appear once the platform is in use." />;
  }

  return (
    <div data-testid="admin-dashboard">
      <AdminPageHeader
        title="Platform overview"
        description="Executive snapshot of users, documents, conversations, tools, and system health."
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {data.metrics.map((metric) => (
          <MetricCard
            key={metric.key}
            label={metric.label}
            value={metric.value}
            unit={metric.unit}
            unavailable={metric.unavailable}
            hint={metric.hint}
          />
        ))}
      </div>

      <div className="mt-8 grid gap-6 xl:grid-cols-2">
        <section className="rounded-2xl border border-white/8 bg-slate-900/40 p-4" data-testid="admin-usage-trend">
          <h3 className="mb-4 text-sm font-semibold text-white">Usage trend</h3>
          {data.usage_trend.length ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.usage_trend}>
                  <CartesianGrid stroke="rgba(148,163,184,0.15)" />
                  <XAxis dataKey="date" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
                  <Area type="monotone" dataKey="messages" stroke="#22d3ee" fill="rgba(34,211,238,0.2)" name="Messages" />
                  <Area type="monotone" dataKey="conversations" stroke="#2dd4bf" fill="rgba(45,212,191,0.15)" name="Conversations" />
                  <Area type="monotone" dataKey="tool_executions" stroke="#818cf8" fill="rgba(129,140,248,0.12)" name="Tools" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState title="No usage yet" />
          )}
        </section>

        <section className="rounded-2xl border border-white/8 bg-slate-900/40 p-4">
          <h3 className="mb-4 text-sm font-semibold text-white">Document pipeline</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.document_pipeline}>
                <CartesianGrid stroke="rgba(148,163,184,0.15)" />
                <XAxis dataKey="status" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
                <Bar dataKey="count" fill="#22d3ee" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <section className="rounded-2xl border border-white/8 bg-slate-900/40 p-4">
          <h3 className="mb-3 text-sm font-semibold text-white">AI activity</h3>
          <dl className="space-y-2 text-sm text-slate-300">
            <div className="flex justify-between"><dt>Provider</dt><dd>{data.ai_activity.provider}</dd></div>
            <div className="flex justify-between"><dt>Model</dt><dd>{data.ai_activity.model}</dd></div>
            <div className="flex justify-between"><dt>Avg latency</dt><dd>{data.ai_activity.average_latency_ms ?? "N/A"}</dd></div>
            <div className="flex justify-between"><dt>Failed</dt><dd>{data.ai_activity.failed_requests ?? 0}</dd></div>
          </dl>
          {data.ai_activity.note ? <p className="mt-3 text-xs text-slate-500">{data.ai_activity.note}</p> : null}
        </section>

        <section className="rounded-2xl border border-white/8 bg-slate-900/40 p-4">
          <h3 className="mb-3 text-sm font-semibold text-white">Tool usage</h3>
          <ul className="space-y-2 text-sm">
            {data.tool_usage.length ? data.tool_usage.map((tool) => (
              <li key={tool.tool_name} className="flex justify-between text-slate-300">
                <span>{tool.tool_name}</span>
                <span>{tool.executions}</span>
              </li>
            )) : <li className="text-slate-500">No tool executions yet</li>}
          </ul>
        </section>

        <section className="rounded-2xl border border-white/8 bg-slate-900/40 p-4">
          <h3 className="mb-3 text-sm font-semibold text-white">System status</h3>
          <div className="space-y-2 text-sm">
            {Object.entries({
              backend: data.system_status.backend,
              postgres: data.system_status.postgres,
              redis: data.system_status.redis,
              ollama: data.system_status.ollama,
              storage: data.system_status.storage,
            }).map(([name, status]) => (
              <div key={name} className="flex items-center justify-between">
                <span className="capitalize text-slate-300">{name}</span>
                <StatusBadge status={status} />
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="mt-6 rounded-2xl border border-white/8 bg-slate-900/40 p-4">
        <h3 className="mb-4 text-sm font-semibold text-white">Recent platform activity</h3>
        <ActivityTimeline items={data.recent_activity} />
      </section>
    </div>
  );
}
