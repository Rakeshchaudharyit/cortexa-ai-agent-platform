"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { useAuth } from "@/components/AuthProvider";
import {
  archiveMemory,
  confirmMemory,
  deleteMemory,
  getMemorySettings,
  listMemories,
  rejectMemory,
  restoreMemory,
  updateMemory,
  updateMemorySettings,
} from "@/services/memories";
import type {
  MemoryCategory,
  MemoryResponse,
  MemorySettingsResponse,
  MemoryStatus,
} from "@/types/api";

const PAGE_SIZE = 20;

const CATEGORIES: MemoryCategory[] = [
  "preference",
  "personal_context",
  "project",
  "instruction",
  "workflow",
  "technical_context",
  "decision",
  "goal",
  "relationship_context",
  "other",
];

const STATUS_TABS: Array<{ id: MemoryStatus | "all"; label: string }> = [
  { id: "active", label: "Active" },
  { id: "proposed", label: "Proposed" },
  { id: "archived", label: "Archived" },
  { id: "all", label: "All" },
];

export default function MemoriesPage() {
  const router = useRouter();
  const { status: authStatus } = useAuth();
  const [items, setItems] = useState<MemoryResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState<MemoryStatus | "all">("active");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<MemorySettingsResponse | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [autoExtractConfirm, setAutoExtractConfirm] = useState(false);

  useEffect(() => {
    if (authStatus === "unauthenticated") {
      router.replace("/login");
    }
  }, [authStatus, router]);

  const load = useCallback(
    async (nextOffset: number) => {
      setLoading(true);
      setError(null);
      const result = await listMemories({
        limit: PAGE_SIZE,
        offset: nextOffset,
        status: statusFilter === "all" ? undefined : statusFilter,
        category: categoryFilter || undefined,
        search: search.trim() || undefined,
      });
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
    },
    [router, statusFilter, categoryFilter, search],
  );

  const loadSettings = useCallback(async () => {
    const result = await getMemorySettings();
    if (result.ok) setSettings(result.data);
  }, []);

  useEffect(() => {
    if (authStatus === "authenticated") {
      void load(0);
      void loadSettings();
    }
  }, [authStatus, load, loadSettings]);

  async function runAction(action: () => Promise<{ ok: boolean; error?: string }>) {
    setError(null);
    const result = await action();
    if (!result.ok) {
      setError(result.error || "Action failed");
      return;
    }
    await load(offset);
    await loadSettings();
  }

  if (authStatus === "loading" || authStatus === "unauthenticated") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-slate-400">Loading…</p>
      </div>
    );
  }

  return (
    <main
      className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-4 py-8"
      data-testid="memories-page"
    >
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Your AI Memory</h1>
          <p className="mt-1 text-sm text-slate-400">
            Review and control information the assistant may use across conversations.
          </p>
          <p className="mt-2 text-xs leading-relaxed text-slate-500" data-testid="memory-privacy-notice">
            Only approved memories associated with your account are used. You can edit, disable,
            archive, or delete them at any time.
          </p>
        </div>
        <Link href="/chat" className="text-sm text-cyan-300 hover:text-cyan-200">
          Back to chat
        </Link>
      </header>

      {settings ? (
        <section
          className="rounded-xl border border-white/10 bg-white/[0.03] p-4"
          data-testid="memory-settings"
        >
          <h2 className="text-sm font-semibold text-slate-100">Memory settings</h2>
          <div className="mt-3 flex flex-col gap-3 text-sm text-slate-300">
            <label className="flex items-center justify-between gap-3">
              <span>Enable long-term memory</span>
              <input
                type="checkbox"
                checked={settings.memory_enabled}
                data-testid="setting-memory-enabled"
                onChange={(e) =>
                  void runAction(async () =>
                    updateMemorySettings({ memory_enabled: e.target.checked }),
                  )
                }
              />
            </label>
            <label className="flex items-center justify-between gap-3">
              <span>Use memory in future chats</span>
              <input
                type="checkbox"
                checked={settings.include_memories_in_chat}
                data-testid="setting-include-in-chat"
                onChange={(e) =>
                  void runAction(async () =>
                    updateMemorySettings({ include_memories_in_chat: e.target.checked }),
                  )
                }
              />
            </label>
            <label className="flex items-center justify-between gap-3">
              <span>Allow memory suggestions</span>
              <input
                type="checkbox"
                checked={settings.suggestions_enabled}
                data-testid="setting-suggestions"
                onChange={(e) =>
                  void runAction(async () =>
                    updateMemorySettings({ suggestions_enabled: e.target.checked }),
                  )
                }
              />
            </label>
            <label className="flex items-center justify-between gap-3">
              <span>Require confirmation before saving</span>
              <input
                type="checkbox"
                checked={settings.require_confirmation}
                data-testid="setting-require-confirmation"
                onChange={(e) =>
                  void runAction(async () =>
                    updateMemorySettings({ require_confirmation: e.target.checked }),
                  )
                }
              />
            </label>
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
              <label className="flex items-start justify-between gap-3">
                <span>
                  Allow automatic extraction
                  <span className="mt-1 block text-xs text-slate-500">
                    Automatically suggest durable preferences and project context from completed
                    conversations. Sensitive information is rejected, and confirmation may still be
                    required.
                  </span>
                </span>
                <input
                  type="checkbox"
                  checked={settings.automatic_extraction_enabled}
                  data-testid="setting-automatic-extraction"
                  onChange={(e) => {
                    if (e.target.checked && !autoExtractConfirm) {
                      setAutoExtractConfirm(true);
                      return;
                    }
                    void runAction(async () =>
                      updateMemorySettings({ automatic_extraction_enabled: e.target.checked }),
                    );
                  }}
                />
              </label>
              {autoExtractConfirm && !settings.automatic_extraction_enabled ? (
                <div className="mt-2 flex flex-wrap gap-2" data-testid="auto-extract-confirm">
                  <p className="w-full text-xs text-amber-100/90">
                    Enable automatic extraction? You can turn it off anytime.
                  </p>
                  <button
                    type="button"
                    className="rounded-md bg-amber-500/20 px-2 py-1 text-xs text-amber-100"
                    onClick={() => {
                      setAutoExtractConfirm(false);
                      void runAction(async () =>
                        updateMemorySettings({ automatic_extraction_enabled: true }),
                      );
                    }}
                  >
                    Enable
                  </button>
                  <button
                    type="button"
                    className="rounded-md bg-slate-500/20 px-2 py-1 text-xs text-slate-200"
                    onClick={() => setAutoExtractConfirm(false)}
                  >
                    Cancel
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </section>
      ) : null}

      <div className="flex flex-wrap gap-2" data-testid="memory-status-tabs">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setStatusFilter(tab.id)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium ring-1 ${
              statusFilter === tab.id
                ? "bg-cyan-500/20 text-cyan-100 ring-cyan-400/40"
                : "bg-slate-500/10 text-slate-300 ring-slate-500/30"
            }`}
            data-testid={`memory-tab-${tab.id}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search memories"
          className="flex-1 rounded-lg border border-white/10 bg-slate-900/60 px-3 py-2 text-sm text-slate-100"
          data-testid="memory-search"
        />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="rounded-lg border border-white/10 bg-slate-900/60 px-3 py-2 text-sm text-slate-100"
          data-testid="memory-category-filter"
        >
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => void load(0)}
          className="rounded-lg bg-cyan-500/20 px-3 py-2 text-sm text-cyan-100 ring-1 ring-cyan-400/30"
          data-testid="memory-search-submit"
        >
          Search
        </button>
      </div>

      {error ? (
        <p
          className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-100"
          role="alert"
          data-testid="memory-error"
        >
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="text-sm text-slate-400">Loading memories…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-400" data-testid="memory-empty">
          No memories in this view yet.
        </p>
      ) : (
        <ul className="flex flex-col gap-3" data-testid="memory-list">
          {items.map((memory) => (
            <li
              key={memory.id}
              className="rounded-xl border border-white/10 bg-white/[0.03] p-4"
              data-testid="memory-item"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="font-medium text-slate-100">{memory.title}</h3>
                  <p className="mt-1 text-xs text-slate-500">
                    {memory.category} · {memory.status} · {memory.source.replaceAll("_", " ")}
                    {memory.confidence ? ` · ${memory.confidence} confidence` : ""}
                  </p>
                </div>
                <p className="text-xs text-slate-500">
                  {memory.last_used_at
                    ? `Last used ${new Date(memory.last_used_at).toLocaleString()}`
                    : "Not used yet"}
                </p>
              </div>
              {editingId === memory.id ? (
                <div className="mt-3 flex flex-col gap-2" data-testid="memory-edit-form">
                  <input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="rounded-md border border-white/10 bg-slate-900/60 px-2 py-1 text-sm"
                    data-testid="memory-edit-title"
                  />
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    rows={3}
                    className="rounded-md border border-white/10 bg-slate-900/60 px-2 py-1 text-sm"
                    data-testid="memory-edit-content"
                  />
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="rounded-md bg-cyan-500/20 px-2 py-1 text-xs text-cyan-100"
                      data-testid="memory-edit-save"
                      onClick={() =>
                        void runAction(async () => {
                          const result = await updateMemory(memory.id, {
                            title: editTitle,
                            content: editContent,
                          });
                          if (result.ok) setEditingId(null);
                          return result;
                        })
                      }
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      className="rounded-md bg-slate-500/20 px-2 py-1 text-xs"
                      onClick={() => setEditingId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <p className="mt-2 text-sm text-slate-300">{memory.content}</p>
              )}
              {memory.expires_at ? (
                <p className="mt-1 text-xs text-slate-500">
                  Expires {new Date(memory.expires_at).toLocaleDateString()}
                </p>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                {memory.status === "proposed" ? (
                  <>
                    <button
                      type="button"
                      className="rounded-md bg-emerald-500/20 px-2 py-1 text-xs text-emerald-100"
                      data-testid="memory-confirm"
                      onClick={() => void runAction(async () => confirmMemory(memory.id))}
                    >
                      Confirm
                    </button>
                    <button
                      type="button"
                      className="rounded-md bg-rose-500/20 px-2 py-1 text-xs text-rose-100"
                      data-testid="memory-reject"
                      onClick={() => void runAction(async () => rejectMemory(memory.id))}
                    >
                      Reject
                    </button>
                  </>
                ) : null}
                {memory.status === "active" ? (
                  <button
                    type="button"
                    className="rounded-md bg-slate-500/20 px-2 py-1 text-xs"
                    data-testid="memory-archive"
                    onClick={() => void runAction(async () => archiveMemory(memory.id))}
                  >
                    Archive
                  </button>
                ) : null}
                {memory.status === "archived" ? (
                  <button
                    type="button"
                    className="rounded-md bg-cyan-500/20 px-2 py-1 text-xs text-cyan-100"
                    data-testid="memory-restore"
                    onClick={() => void runAction(async () => restoreMemory(memory.id))}
                  >
                    Restore
                  </button>
                ) : null}
                {memory.status !== "deleted" ? (
                  <>
                    <button
                      type="button"
                      className="rounded-md bg-slate-500/20 px-2 py-1 text-xs"
                      data-testid="memory-edit"
                      onClick={() => {
                        setEditingId(memory.id);
                        setEditTitle(memory.title);
                        setEditContent(memory.content);
                      }}
                    >
                      Edit
                    </button>
                    {confirmDeleteId === memory.id ? (
                      <button
                        type="button"
                        className="rounded-md bg-rose-500/30 px-2 py-1 text-xs text-rose-100"
                        data-testid="memory-delete-confirm"
                        onClick={() =>
                          void runAction(async () => {
                            const result = await deleteMemory(memory.id);
                            if (result.ok) setConfirmDeleteId(null);
                            return result;
                          })
                        }
                      >
                        Confirm delete
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="rounded-md bg-rose-500/20 px-2 py-1 text-xs text-rose-100"
                        data-testid="memory-delete"
                        onClick={() => setConfirmDeleteId(memory.id)}
                      >
                        Delete
                      </button>
                    )}
                  </>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-center justify-between text-sm text-slate-400">
        <span>
          Showing {items.length} of {total}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={offset <= 0}
            onClick={() => void load(Math.max(0, offset - PAGE_SIZE))}
            className="rounded-md bg-slate-500/20 px-2 py-1 disabled:opacity-40"
          >
            Previous
          </button>
          <button
            type="button"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => void load(offset + PAGE_SIZE)}
            className="rounded-md bg-slate-500/20 px-2 py-1 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </main>
  );
}
