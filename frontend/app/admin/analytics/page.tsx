"use client";

import { useEffect, useState } from "react";
import {
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
    return () => {
      cancelled = true;
    };
  }, [days]);

  return (
    <div data-testid="admin-analytics-page">
      <AdminPageHeader
        title="Analytics"
        description="Bounded aggregates over recent platform activity. Private content is never included."
        actions={
          <div className="flex gap-2" data-testid="admin-analytics-range">
            {[7, 30, 90].map((value) => (
              <button
                key={value}
                type="button"
                className={`rounded-lg px-3 py-2 text-sm ring-1 ${
                  days === value
                    ? "bg-cyan-500/20 text-cyan-100 ring-cyan-400/40"
                    : "bg-slate-800 text-slate-200 ring-white/10"
                }`}
                onClick={() => setDays(value as 7 | 30 | 90)}
              >
                {value}d
              </button>
            ))}
          </div>
        }
      />
      {loading ? (
        <div className="h-64 animate-pulse rounded-2xl bg-slate-800/40" />
      ) : !data ? (
        <EmptyState title="Analytics unavailable" />
      ) : (
        <>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="New users" value={Number(data.totals.new_users || 0)} />
            <MetricCard label="Conversations" value={Number(data.totals.conversations || 0)} />
            <MetricCard label="Messages" value={Number(data.totals.messages || 0)} />
            <MetricCard label="Tool executions" value={Number(data.totals.tool_executions || 0)} />
          </div>
          <div className="h-80 rounded-2xl border border-white/8 bg-slate-900/40 p-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.points}>
                <CartesianGrid stroke="rgba(148,163,184,0.15)" />
                <XAxis dataKey="date" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
                <Line type="monotone" dataKey="messages" stroke="#22d3ee" dot={false} />
                <Line type="monotone" dataKey="conversations" stroke="#2dd4bf" dot={false} />
                <Line type="monotone" dataKey="tool_executions" stroke="#818cf8" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          {data.unavailable.length ? (
            <p className="mt-3 text-xs text-slate-500">
              Unavailable series: {data.unavailable.join(", ")}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
