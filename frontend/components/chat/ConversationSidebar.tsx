"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";

import {
  archiveConversation,
  createConversation,
  deleteConversation,
  listConversations,
  renameConversation,
  unarchiveConversation,
} from "@/services/conversations";
import type { ConversationSummary } from "@/types/api";

type Props = {
  activeId: string | null;
  onNewConversation: (id: string) => void;
};

type ConfirmAction =
  | { kind: "delete"; conv: ConversationSummary }
  | { kind: "archive"; conv: ConversationSummary }
  | null;

function formatTime(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return date.toLocaleDateString([], { weekday: "short" });
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function ConversationSidebar({ activeId, onNewConversation }: Props) {
  const router = useRouter();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQ, setSearchQ] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmAction>(null);
  const [renaming, setRenaming] = useState<{ id: string; draft: string } | null>(null);
  const [creatingNew, setCreatingNew] = useState(false);
  const renameInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const result = await listConversations({
      include_archived: showArchived,
      q: searchQ || undefined,
      limit: 50,
    });
    setLoading(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setConversations(result.data.items);
  }, [showArchived, searchQ]);

  useEffect(() => {
    void load();
  }, [load]);

  // Focus rename input when it opens.
  useEffect(() => {
    if (renaming) {
      setTimeout(() => renameInputRef.current?.focus(), 50);
    }
  }, [renaming]);

  async function handleNewChat() {
    setCreatingNew(true);
    const result = await createConversation();
    setCreatingNew(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    const newConv = result.data;
    setConversations((prev) => [newConv, ...prev]);
    onNewConversation(newConv.id);
  }

  async function handleRenameSubmit(id: string, title: string) {
    if (!title.trim()) return;
    const result = await renameConversation(id, title.trim());
    setRenaming(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setConversations((prev) => prev.map((c) => (c.id === id ? result.data : c)));
  }

  async function handleArchive(conv: ConversationSummary) {
    setConfirm(null);
    const result =
      conv.status === "archived"
        ? await unarchiveConversation(conv.id)
        : await archiveConversation(conv.id);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    await load();
  }

  async function handleDelete(conv: ConversationSummary) {
    setConfirm(null);
    const result = await deleteConversation(conv.id);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setConversations((prev) => prev.filter((c) => c.id !== conv.id));
    if (activeId === conv.id) {
      router.push("/chat");
    }
  }

  const active = conversations.filter((c) => c.status === "active");
  const archived = conversations.filter((c) => c.status === "archived");

  return (
    <aside
      className="flex h-full w-full min-w-0 flex-col border-r border-white/10 bg-slate-950/55 backdrop-blur-xl md:w-72 xl:w-80"
      aria-label="Conversations sidebar"
      data-testid="conversation-sidebar"
    >
      {/* Header */}
      <div className="border-b border-white/[0.07] p-3">
        <button
          type="button"
          onClick={() => void handleNewChat()}
          disabled={creatingNew}
          className="w-full rounded-xl bg-cyan-400 px-3 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="new-chat-button"
          aria-label="New chat"
        >
          {creatingNew ? "Creating…" : "+ New Chat"}
        </button>
      </div>

      {/* Search */}
      <div className="border-b border-white/10 p-3">
        <input
          type="search"
          placeholder="Search conversations…"
          value={searchQ}
          onChange={(e) => setSearchQ(e.target.value)}
          className="w-full rounded-xl border border-white/10 bg-white/[0.035] px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 outline-none transition focus:border-cyan-400/25 focus:bg-white/[0.05]"
          aria-label="Search conversations"
          data-testid="conversation-search"
        />
      </div>

      {/* Archived toggle */}
      <div className="flex items-center justify-between border-b border-white/[0.07] px-3 py-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-600">Conversations</span>
        <button
          type="button"
          onClick={() => setShowArchived((v) => !v)}
          className="text-xs text-slate-500 transition hover:text-slate-200"
          data-testid="archived-toggle"
        >
          {showArchived ? "Hide archived" : "Show archived"}
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto py-1" role="list" aria-label="Conversation list">
        {loading && (
          <p className="px-4 py-3 text-sm text-slate-400" data-testid="sidebar-loading">
            Loading…
          </p>
        )}
        {!loading && error && (
          <div className="px-4 py-3">
            <p className="text-sm text-rose-300" data-testid="sidebar-error">{error}</p>
            <button
              type="button"
              onClick={() => void load()}
              className="mt-2 text-xs text-cyan-300 hover:text-cyan-200"
            >
              Retry
            </button>
          </div>
        )}
        {!loading && !error && conversations.length === 0 && (
          <p className="px-4 py-6 text-sm text-slate-500 text-center" data-testid="sidebar-empty">
            No conversations yet.
            <br />Start a new chat above.
          </p>
        )}

        {active.map((conv) => (
          <ConversationItem
            key={conv.id}
            conv={conv}
            isActive={conv.id === activeId}
            renaming={renaming}
            renameInputRef={renameInputRef}
            onSelect={() => router.push(`/chat/${conv.id}`)}
            onStartRename={() => setRenaming({ id: conv.id, draft: conv.title })}
            onRenameChange={(draft) => setRenaming({ id: conv.id, draft })}
            onRenameSubmit={(title) => void handleRenameSubmit(conv.id, title)}
            onRenameCancel={() => setRenaming(null)}
            onArchive={() => setConfirm({ kind: "archive", conv })}
            onDelete={() => setConfirm({ kind: "delete", conv })}
          />
        ))}

        {showArchived && archived.length > 0 && (
          <>
            <p className="mt-3 px-3 pb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Archived
            </p>
            {archived.map((conv) => (
              <ConversationItem
                key={conv.id}
                conv={conv}
                isActive={conv.id === activeId}
                renaming={renaming}
                renameInputRef={renameInputRef}
                onSelect={() => router.push(`/chat/${conv.id}`)}
                onStartRename={() => setRenaming({ id: conv.id, draft: conv.title })}
                onRenameChange={(draft) => setRenaming({ id: conv.id, draft })}
                onRenameSubmit={(title) => void handleRenameSubmit(conv.id, title)}
                onRenameCancel={() => setRenaming(null)}
                onArchive={() => setConfirm({ kind: "archive", conv })}
                onDelete={() => setConfirm({ kind: "delete", conv })}
              />
            ))}
          </>
        )}
      </div>

      {/* Confirmation dialog */}
      {confirm && (
        <ConfirmDialog
          action={confirm}
          onConfirm={() => {
            if (confirm.kind === "delete") void handleDelete(confirm.conv);
            else void handleArchive(confirm.conv);
          }}
          onCancel={() => setConfirm(null)}
        />
      )}
    </aside>
  );
}

// ─── ConversationItem ─────────────────────────────────────────────────────────

type ItemProps = {
  conv: ConversationSummary;
  isActive: boolean;
  renaming: { id: string; draft: string } | null;
  renameInputRef: React.RefObject<HTMLInputElement | null>;
  onSelect: () => void;
  onStartRename: () => void;
  onRenameChange: (draft: string) => void;
  onRenameSubmit: (title: string) => void;
  onRenameCancel: () => void;
  onArchive: () => void;
  onDelete: () => void;
};

function ConversationItem({
  conv,
  isActive,
  renaming,
  renameInputRef,
  onSelect,
  onStartRename,
  onRenameChange,
  onRenameSubmit,
  onRenameCancel,
  onArchive,
  onDelete,
}: ItemProps) {
  const isRenaming = renaming?.id === conv.id;
  const time = formatTime(conv.last_message_at ?? conv.updated_at);

  function handleKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      onRenameSubmit(renaming?.draft ?? "");
    } else if (e.key === "Escape") {
      onRenameCancel();
    }
  }

  return (
    <div
      role="listitem"
      data-testid={`conversation-item-${conv.id}`}
      className={`group relative mx-2 my-1 flex cursor-pointer flex-col gap-0.5 rounded-xl px-3 py-2.5 transition hover:bg-white/[0.045] ${
        isActive ? "bg-cyan-400/[0.08] ring-1 ring-inset ring-cyan-400/15" : ""
      }`}
      onClick={isRenaming ? undefined : onSelect}
      onKeyDown={(e) => {
        if (!isRenaming && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onSelect();
        }
      }}
      tabIndex={isRenaming ? -1 : 0}
      aria-current={isActive ? "page" : undefined}
      aria-label={`Conversation: ${conv.title}`}
    >
      {isRenaming ? (
        <input
          ref={renameInputRef}
          type="text"
          value={renaming.draft}
          onChange={(e) => onRenameChange(e.target.value)}
          onKeyDown={handleKey}
          onBlur={() => onRenameSubmit(renaming.draft)}
          className="w-full rounded bg-slate-800 px-2 py-1 text-sm text-slate-100 outline-none ring-1 ring-cyan-400/50"
          aria-label="Rename conversation"
          data-testid={`rename-input-${conv.id}`}
        />
      ) : (
        <span className="truncate text-sm text-slate-100 font-medium" data-testid={`conv-title-${conv.id}`}>
          {conv.title}
        </span>
      )}
      <span className="text-xs text-slate-500">{time}</span>

      {/* Context menu — visible on hover / active */}
      {!isRenaming && (
        <div
          className="absolute right-2 top-2 hidden items-center gap-0.5 group-hover:flex group-focus-within:flex"
          onClick={(e) => e.stopPropagation()}
        >
          <ActionButton label="Rename" onClick={onStartRename} testId={`rename-btn-${conv.id}`}>
            ✎
          </ActionButton>
          <ActionButton
            label={conv.status === "archived" ? "Unarchive" : "Archive"}
            onClick={onArchive}
            testId={`archive-btn-${conv.id}`}
          >
            {conv.status === "archived" ? "↑" : "⊡"}
          </ActionButton>
          <ActionButton
            label="Delete"
            onClick={onDelete}
            testId={`delete-btn-${conv.id}`}
            danger
          >
            ✕
          </ActionButton>
        </div>
      )}
    </div>
  );
}

function ActionButton({
  label,
  onClick,
  testId,
  danger,
  children,
}: {
  label: string;
  onClick: () => void;
  testId: string;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      data-testid={testId}
      className={`flex h-6 w-6 items-center justify-center rounded text-xs transition ${
        danger
          ? "text-slate-500 hover:bg-rose-500/20 hover:text-rose-300"
          : "text-slate-500 hover:bg-white/10 hover:text-slate-200"
      }`}
    >
      {children}
    </button>
  );
}

// ─── ConfirmDialog ────────────────────────────────────────────────────────────

function ConfirmDialog({
  action,
  onConfirm,
  onCancel,
}: {
  action: NonNullable<ConfirmAction>;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const isDelete = action.kind === "delete";
  const isArchived = action.conv.status === "archived";

  const message = isDelete
    ? `Delete "${action.conv.title}"? This cannot be undone.`
    : isArchived
      ? `Unarchive "${action.conv.title}"?`
      : `Archive "${action.conv.title}"?`;

  return (
    <div
      className="absolute inset-0 z-20 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Confirm action"
      data-testid="confirm-dialog"
    >
      <div className="mx-4 rounded-xl border border-white/10 bg-slate-900 p-4 shadow-xl">
        <p className="text-sm text-slate-200">{message}</p>
        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 transition"
            data-testid="confirm-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              isDelete
                ? "bg-rose-500/20 text-rose-200 hover:bg-rose-500/30"
                : "bg-cyan-500/20 text-cyan-200 hover:bg-cyan-500/30"
            }`}
            data-testid="confirm-ok"
          >
            {isDelete ? "Delete" : isArchived ? "Unarchive" : "Archive"}
          </button>
        </div>
      </div>
    </div>
  );
}
