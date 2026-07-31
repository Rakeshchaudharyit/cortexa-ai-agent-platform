"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { useAuth } from "@/components/AuthProvider";
import { listToolExecutions } from "@/services/tools";
import type { ToolExecutionSummary } from "@/types/api";
import { ToolExecutionCard } from "@/components/chat/ToolExecutionCard";

const PAGE_SIZE = 20;

export default function ToolExecutionsPage() {
  const router = useRouter();
  const { status } = useAuth();
  const [items, setItems] = useState<ToolExecutionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  const load = useCallback(async (nextOffset: number) => {
    setLoading(true);
    setError(null);
    const result = await listToolExecutions({ limit: PAGE_SIZE, offset: nextOffset });
    setLoading(false);
    if (!result.ok) {
      if (result.status === 401) {
        router.replace("/login");
        return;
      }
      setError(result.error);
      return;
    }
    setItems(result.data.items);
    setTotal(result.data.total);
    setOffset(result.data.offset);
  }, [router]);

  useEffect(() => {
    if (status === "authenticated") {
      void load(0);
    }
  }, [status, load]);

  if (status === "loading" || status === "unauthenticated") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-slate-400">Loading…</p>
      </div>
    );
  }

  const canPrev = offset > 0;
  const canNext = offset + PAGE_SIZE < total;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-4 py-8" data-testid="tools-page">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Tool executions</h1>
          <p className="mt-1 text-sm text-slate-400">
            Your recent agent tool activity. Only your own records are shown.
          </p>
        </div>
        <Link href="/chat" className="text-sm text-cyan-300 hover:text-cyan-200">
          Back to chat
        </Link>
      </header>

      {error && (
        <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-100" role="alert">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-sm text-slate-400" data-testid="tools-loading">Loading executions…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-400" data-testid="tools-empty">No tool executions yet.</p>
      ) : (
        <div className="flex flex-col gap-3" data-testid="tools-list">
          {items.map((item) => (
            <div key={item.id} className="rounded-2xl border border-white/10 bg-slate-900/40 p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
                <span>{new Date(item.started_at).toLocaleString()}</span>
                <span>{item.duration_ms != null ? `${item.duration_ms} ms` : "—"}</span>
              </div>
              <ToolExecutionCard activity={item} />
              {item.conversation_id && (
                <Link
                  href={`/chat/${item.conversation_id}`}
                  className="mt-2 inline-block text-xs text-cyan-300/90 hover:text-cyan-200"
                >
                  Open conversation
                </Link>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          disabled={!canPrev || loading}
          onClick={() => void load(Math.max(0, offset - PAGE_SIZE))}
          className="rounded-lg border border-white/10 px-3 py-1.5 text-sm text-slate-200 disabled:opacity-40"
          data-testid="tools-prev"
        >
          Previous
        </button>
        <p className="text-xs text-slate-500" data-testid="tools-page-info">
          {total === 0 ? "0" : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)}`} of {total}
        </p>
        <button
          type="button"
          disabled={!canNext || loading}
          onClick={() => void load(offset + PAGE_SIZE)}
          className="rounded-lg border border-white/10 px-3 py-1.5 text-sm text-slate-200 disabled:opacity-40"
          data-testid="tools-next"
        >
          Next
        </button>
      </div>
    </main>
  );
}
