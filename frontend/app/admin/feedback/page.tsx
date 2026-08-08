"use client";

import { useEffect, useMemo, useState } from "react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { MetricCard } from "@/components/admin/MetricCard";
import { fetchAdminFeedback, updateAdminFeedback } from "@/services/admin";
import type { AdminFeedbackItem, AdminFeedbackList } from "@/types/admin";

const EMPTY: AdminFeedbackList = {
  items: [], total: 0, open_count: 0, helpful_count: 0, not_helpful_count: 0,
};

const REASON_LABELS: Record<string, string> = {
  incorrect: "Incorrect answer",
  missing_source: "Missing or wrong source",
  not_relevant: "Not relevant",
  incomplete: "Incomplete",
  unclear: "Unclear",
  other: "Other",
};

function statusClass(status: AdminFeedbackItem["status"]) {
  if (status === "resolved") return "border-emerald-400/20 bg-emerald-500/10 text-emerald-200";
  if (status === "reviewed") return "border-amber-400/20 bg-amber-500/10 text-amber-200";
  return "border-cyan-400/20 bg-cyan-500/10 text-cyan-200";
}

export default function AdminFeedbackPage() {
  const [data, setData] = useState<AdminFeedbackList>(EMPTY);
  const [status, setStatus] = useState("");
  const [sentiment, setSentiment] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  async function load() {
    setLoading(true);
    setError(null);
    const result = await fetchAdminFeedback({ status: status || undefined, sentiment: sentiment || undefined });
    if (result.ok) {
      setData(result.data);
      setNotes(Object.fromEntries(result.data.items.map((item) => [item.id, item.admin_note ?? ""])));
    } else {
      setError(result.error.message);
    }
    setLoading(false);
  }

  useEffect(() => { void load(); }, [status, sentiment]);

  async function setReviewState(item: AdminFeedbackItem, next: "open" | "reviewed" | "resolved") {
    setSavingId(item.id);
    setError(null);
    setSuccess(null);
    const result = await updateAdminFeedback(item.id, {
      status: next,
      admin_note: notes[item.id]?.trim() || undefined,
    });
    if (result.ok) {
      setData((current) => ({
        ...current,
        open_count: current.open_count + (item.status === "open" && next !== "open" ? -1 : item.status !== "open" && next === "open" ? 1 : 0),
        items: current.items.map((entry) => entry.id === item.id ? result.data : entry),
      }));
      setSuccess(`Feedback marked ${next}.`);
    } else {
      setError(result.error.message);
    }
    setSavingId(null);
  }

  const helpfulRate = data.total > 0 ? Math.round((data.helpful_count / data.total) * 100) : null;
  const reviewProgress = data.total > 0 ? Math.round(((data.total - data.open_count) / data.total) * 100) : null;
  const filterSummary = useMemo(() => {
    const bits = [];
    if (status) bits.push(status);
    if (sentiment) bits.push(sentiment.replaceAll("_", " "));
    return bits.length ? bits.join(" · ") : "All feedback";
  }, [status, sentiment]);

  return (
    <div data-testid="admin-feedback-page">
      <AdminPageHeader
        title="Answer Feedback"
        description="Human-in-the-loop review for helpfulness, source quality, and reported AI response issues."
      />

      <section className="mb-6 overflow-hidden rounded-3xl border border-violet-400/15 bg-gradient-to-br from-violet-500/10 via-slate-950/70 to-cyan-500/5 p-6 shadow-[0_22px_70px_rgba(0,0,0,0.22)]">
        <div className="grid gap-6 lg:grid-cols-[1.25fr_.75fr] lg:items-end">
          <div>
            <p className="cx-eyebrow">Human quality review</p>
            <h3 className="mt-3 max-w-3xl text-2xl font-semibold tracking-tight text-white sm:text-3xl">Turn user feedback into an auditable AI improvement workflow.</h3>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">Review reported answers, capture an internal resolution note, and close issues without exposing prompts, private source passages, or hidden reasoning.</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-2xl border border-white/10 bg-slate-950/45 p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Helpful rate</p>
              <p className="mt-2 text-3xl font-semibold text-white">{helpfulRate === null ? "—" : `${helpfulRate}%`}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-950/45 p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Review progress</p>
              <p className="mt-2 text-3xl font-semibold text-white">{reviewProgress === null ? "—" : `${reviewProgress}%`}</p>
            </div>
          </div>
        </div>
      </section>

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Feedback received" value={data.total} hint="All rated AI responses" />
        <MetricCard label="Open reviews" value={data.open_count} hint="Waiting for admin action" />
        <MetricCard label="Helpful" value={data.helpful_count} hint="Positive quality signal" />
        <MetricCard label="Needs attention" value={data.not_helpful_count} hint="Reported or unhelpful responses" />
      </div>

      <section className="mb-6 cx-panel p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Review queue</p>
            <p className="mt-1 text-sm text-slate-300">{filterSummary} · {data.items.length} visible</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <label className="text-xs font-medium uppercase tracking-wide text-slate-500">
              <span className="sr-only">Status</span>
              <select value={status} onChange={(e) => setStatus(e.target.value)} className="cx-input min-w-36 py-2 text-sm normal-case tracking-normal">
                <option value="">All statuses</option><option value="open">Open</option><option value="reviewed">Reviewed</option><option value="resolved">Resolved</option>
              </select>
            </label>
            <label className="text-xs font-medium uppercase tracking-wide text-slate-500">
              <span className="sr-only">Rating</span>
              <select value={sentiment} onChange={(e) => setSentiment(e.target.value)} className="cx-input min-w-40 py-2 text-sm normal-case tracking-normal">
                <option value="">All ratings</option><option value="helpful">Helpful</option><option value="not_helpful">Not helpful</option>
              </select>
            </label>
          </div>
        </div>
      </section>

      {success ? <div className="mb-4 rounded-2xl border border-emerald-400/15 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100" role="status">{success}</div> : null}
      {error ? <div className="mb-4 rounded-2xl border border-rose-400/15 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">{error}</div> : null}

      {loading ? (
        <div className="space-y-4" aria-label="Loading feedback">
          {[0, 1, 2].map((item) => <div key={item} className="h-52 animate-pulse rounded-2xl border border-white/8 bg-white/[0.025]" />)}
        </div>
      ) : null}

      {!loading && data.items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] px-6 py-12 text-center">
          <p className="text-sm font-medium text-slate-200">No feedback matches these filters</p>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">Change the filters or wait for users to rate completed AI responses. Open quality issues will appear here automatically.</p>
        </div>
      ) : null}

      <div className="space-y-4">
        {data.items.map((item) => (
          <article key={item.id} className="overflow-hidden rounded-2xl border border-white/8 bg-slate-950/45 shadow-[0_14px_40px_rgba(0,0,0,0.14)]">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/5 px-5 py-4">
              <div className="flex items-start gap-3">
                <div className={`mt-0.5 flex size-9 items-center justify-center rounded-xl border text-sm font-bold ${item.sentiment === "helpful" ? "border-emerald-400/20 bg-emerald-500/10 text-emerald-200" : "border-rose-400/20 bg-rose-500/10 text-rose-200"}`} aria-hidden="true">
                  {item.sentiment === "helpful" ? "+" : "!"}
                </div>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className={`text-sm font-semibold ${item.sentiment === "helpful" ? "text-emerald-200" : "text-rose-200"}`}>{item.sentiment === "helpful" ? "Helpful response" : "Response needs attention"}</p>
                    {item.reason ? <span className="rounded-full border border-white/8 bg-white/[0.035] px-2 py-0.5 text-[10px] font-medium text-slate-400">{REASON_LABELS[item.reason] ?? item.reason.replaceAll("_", " ")}</span> : null}
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{item.user_email} · {new Date(item.created_at).toLocaleString()}</p>
                </div>
              </div>
              <span className={`rounded-full border px-2.5 py-1 text-xs font-medium capitalize ${statusClass(item.status)}`}>{item.status}</span>
            </div>

            <div className="grid gap-5 px-5 py-5 lg:grid-cols-[1.2fr_.8fr]">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Answer excerpt</p>
                <blockquote className="mt-2 rounded-xl border border-white/8 bg-white/[0.025] p-4 text-sm leading-6 text-slate-200">{item.answer_excerpt}</blockquote>
                {item.comment ? (
                  <div className="mt-3 rounded-xl border border-amber-400/10 bg-amber-500/[0.055] p-3 text-sm text-slate-300">
                    <span className="block text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-300/70">User context</span>
                    <p className="mt-1 leading-6">{item.comment}</p>
                  </div>
                ) : null}
                <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-500">
                  <span className="rounded-full border border-white/8 px-2.5 py-1">{item.provider ?? "Unknown provider"}</span>
                  <span className="rounded-full border border-white/8 px-2.5 py-1">{item.model ?? "Unknown model"}</span>
                  <span className="rounded-full border border-white/8 px-2.5 py-1">{item.citation_count} citation{item.citation_count === 1 ? "" : "s"}</span>
                  <span className={`rounded-full border px-2.5 py-1 ${item.grounded ? "border-emerald-400/15 text-emerald-300" : "border-white/8"}`}>{item.grounded ? "Grounded" : "Grounding unavailable"}</span>
                </div>
              </div>

              <div className="rounded-xl border border-white/8 bg-white/[0.02] p-4">
                <label className="block text-xs font-medium uppercase tracking-[0.14em] text-slate-500" htmlFor={`review-note-${item.id}`}>Internal review note</label>
                <textarea id={`review-note-${item.id}`} value={notes[item.id] ?? ""} onChange={(event) => setNotes((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="Record the finding, correction, or follow-up action…" maxLength={2000} className="cx-input mt-3 min-h-28 resize-y" />
                <p className="mt-2 text-xs leading-5 text-slate-500">Visible only to administrators. Keep notes concise and action-oriented.</p>
                <div className="mt-4 grid gap-2 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
                  <button disabled={savingId === item.id || item.status === "open"} onClick={() => void setReviewState(item, "open")} className="cx-button-secondary min-h-9 px-3 py-1.5 text-xs">Reopen</button>
                  <button disabled={savingId === item.id || item.status === "reviewed"} onClick={() => void setReviewState(item, "reviewed")} className="inline-flex min-h-9 items-center justify-center rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-200 transition hover:bg-amber-500/15 disabled:cursor-not-allowed disabled:opacity-40">Mark reviewed</button>
                  <button disabled={savingId === item.id || item.status === "resolved"} onClick={() => void setReviewState(item, "resolved")} className="inline-flex min-h-9 items-center justify-center rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-200 transition hover:bg-emerald-500/15 disabled:cursor-not-allowed disabled:opacity-40">Resolve</button>
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
