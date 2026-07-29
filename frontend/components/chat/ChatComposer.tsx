"use client";

import { type KeyboardEvent, useRef, useState } from "react";

const MAX_LENGTH = 100_000;

type DocumentScope = "all" | "none" | "selected";

type Props = {
  disabled?: boolean;
  isStreaming?: boolean;
  availableDocumentIds?: string[];
  onSend: (content: string, documentIds: string[] | null) => void;
  onCancel?: () => void;
};

export function ChatComposer({
  disabled,
  isStreaming,
  availableDocumentIds,
  onSend,
  onCancel,
}: Props) {
  const [draft, setDraft] = useState("");
  const [docScope, setDocScope] = useState<DocumentScope>("all");
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const len = draft.length;
  const overLimit = len > MAX_LENGTH;
  const canSend = draft.trim().length > 0 && !disabled && !isStreaming && !overLimit;

  function resolveDocumentIds(): string[] | null {
    if (docScope === "all") return null;        // null = all owned documents
    if (docScope === "none") return [];          // [] = general LLM (no retrieval)
    return Array.from(selectedDocs);             // explicit IDs
  }

  function handleSend() {
    if (!canSend) return;
    const content = draft.trim();
    const ids = resolveDocumentIds();
    setDraft("");
    onSend(content, ids);
  }

  function handleKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function toggleDoc(id: string) {
    setSelectedDocs((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <section
      className="border-t border-white/10 bg-black/20 p-3"
      aria-label="Message composer"
      data-testid="chat-composer"
    >
      {/* Document scope control */}
      {availableDocumentIds && availableDocumentIds.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-2" data-testid="doc-scope-control">
          <span className="text-xs text-slate-500">Sources:</span>
          <ScopeButton active={docScope === "all"} onClick={() => setDocScope("all")}>
            All documents
          </ScopeButton>
          <ScopeButton active={docScope === "none"} onClick={() => setDocScope("none")}>
            General chat (no docs)
          </ScopeButton>
          <ScopeButton
            active={docScope === "selected"}
            onClick={() => setDocScope("selected")}
          >
            Selected…
          </ScopeButton>
          {docScope === "selected" && (
            <div className="flex flex-wrap gap-1 mt-1 w-full" data-testid="doc-selector">
              {availableDocumentIds.map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => toggleDoc(id)}
                  className={`rounded px-2 py-0.5 text-xs transition ring-1 ${
                    selectedDocs.has(id)
                      ? "bg-cyan-500/20 text-cyan-200 ring-cyan-400/30"
                      : "bg-slate-800/60 text-slate-400 ring-white/10 hover:text-slate-200"
                  }`}
                  aria-pressed={selectedDocs.has(id)}
                  aria-label={`Toggle document ${id}`}
                >
                  {id.slice(0, 8)}…
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Textarea row */}
      <div className="flex items-end gap-2">
        <div className="relative flex-1">
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKey}
            disabled={disabled && !isStreaming}
            rows={1}
            placeholder="Message Cortexa… (Enter to send, Shift+Enter for newline)"
            aria-label="Message input"
            data-testid="composer-input"
            className="w-full resize-none overflow-hidden rounded-xl border border-white/10 bg-slate-950/50 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 outline-none ring-cyan-400/0 transition focus:ring-1 focus:ring-cyan-400/40 disabled:cursor-not-allowed disabled:opacity-50"
            style={{ minHeight: "3rem", maxHeight: "14rem" }}
            onInput={(e) => {
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 224)}px`;
            }}
          />
        </div>

        {isStreaming ? (
          <button
            type="button"
            onClick={onCancel}
            className="shrink-0 rounded-xl bg-rose-500/15 px-4 py-3 text-sm font-medium text-rose-200 ring-1 ring-rose-400/25 transition hover:bg-rose-500/25"
            data-testid="cancel-stream-button"
            aria-label="Cancel streaming"
          >
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSend}
            disabled={!canSend}
            className="shrink-0 rounded-xl bg-cyan-500/15 px-4 py-3 text-sm font-medium text-cyan-100 ring-1 ring-cyan-400/25 transition hover:bg-cyan-500/25 disabled:cursor-not-allowed disabled:opacity-40"
            data-testid="send-button"
            aria-label="Send message"
          >
            Send
          </button>
        )}
      </div>

      {/* Character count feedback */}
      {len > MAX_LENGTH * 0.8 && (
        <p
          className={`mt-1 text-right text-xs ${overLimit ? "text-rose-400" : "text-slate-500"}`}
          role={overLimit ? "alert" : undefined}
          data-testid="char-count"
        >
          {len.toLocaleString()} / {MAX_LENGTH.toLocaleString()}
        </p>
      )}
    </section>
  );
}

function ScopeButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded px-2 py-0.5 text-xs transition ring-1 ${
        active
          ? "bg-cyan-500/20 text-cyan-200 ring-cyan-400/30"
          : "bg-slate-800/60 text-slate-400 ring-white/10 hover:text-slate-200"
      }`}
    >
      {children}
    </button>
  );
}
