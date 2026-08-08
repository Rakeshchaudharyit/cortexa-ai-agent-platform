"use client";

import { type KeyboardEvent, useRef, useState } from "react";

const MAX_LENGTH = 100_000;

type ChatMode = "general" | "documents";
type DocumentScope = "all" | "selected";

export type ComposerDocument = {
  id: string;
  label: string;
};

type Props = {
  disabled?: boolean;
  isStreaming?: boolean;
  availableDocuments?: ComposerDocument[];
  onSend: (content: string, documentIds: string[] | null) => void;
  onCancel?: () => void;
};

export function ChatComposer({
  disabled,
  isStreaming,
  availableDocuments = [],
  onSend,
  onCancel,
}: Props) {
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<ChatMode>("general");
  const [docScope, setDocScope] = useState<DocumentScope>("all");
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const len = draft.length;
  const overLimit = len > MAX_LENGTH;
  const canSend = draft.trim().length > 0 && !disabled && !isStreaming && !overLimit;

  function resolveDocumentIds(): string[] | null {
    if (mode === "general") return [];
    if (docScope === "all") return null;
    return Array.from(selectedDocs);
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
      className="border-t border-white/10 bg-slate-950/70 px-3 py-3 backdrop-blur-xl sm:px-5 sm:py-4"
      aria-label="Message composer"
      data-testid="chat-composer"
    >
      <div className="mx-auto w-full max-w-5xl">
        <div className="mb-3 flex flex-col gap-3" data-testid="chat-mode-control">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="inline-flex rounded-xl border border-white/10 bg-white/[0.025] p-1">
              <ScopeButton
                active={mode === "general"}
                onClick={() => setMode("general")}
                testId="mode-general-agent"
              >
                General Agent
              </ScopeButton>
              <ScopeButton
                active={mode === "documents"}
                onClick={() => setMode("documents")}
                testId="mode-document-knowledge"
              >
                Document Knowledge
              </ScopeButton>
            </div>
            <p className="hidden text-[11px] text-slate-600 sm:block">Enter to send · Shift+Enter for a new line</p>
          </div>

          {mode === "general" ? (
            <div className="flex items-start gap-2 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5" data-testid="general-agent-hint">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-400" />
              <p className="text-xs leading-5 text-slate-500">
                Use AI chat and approved tools. Document retrieval is skipped so agent tools can run.
              </p>
            </div>
          ) : (
            <div className="rounded-xl border border-cyan-400/10 bg-cyan-400/[0.035] px-3 py-2.5">
              <div className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400" />
                <p className="text-xs leading-5 text-slate-400" data-testid="document-knowledge-hint">
                  Ask questions grounded in selected documents. Agent tools are not used in this mode when retrieval finds no context.
                </p>
              </div>
              {availableDocuments.length > 0 ? (
                <div className="mt-2.5 flex flex-wrap items-center gap-2" data-testid="doc-scope-control">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-slate-600">Sources</span>
                  <ScopeButton active={docScope === "all"} onClick={() => setDocScope("all")}>
                    All documents
                  </ScopeButton>
                  <ScopeButton active={docScope === "selected"} onClick={() => setDocScope("selected")}>
                    Selected…
                  </ScopeButton>
                  {docScope === "selected" && (
                    <div className="mt-1 flex w-full flex-wrap gap-1.5 border-t border-white/[0.06] pt-2.5" data-testid="doc-selector">
                      {availableDocuments.map((doc) => (
                        <button
                          key={doc.id}
                          type="button"
                          onClick={() => toggleDoc(doc.id)}
                          className={`max-w-full truncate rounded-lg px-2.5 py-1.5 text-xs transition ring-1 ${
                            selectedDocs.has(doc.id)
                              ? "bg-cyan-400/10 text-cyan-100 ring-cyan-400/25"
                              : "bg-slate-950/50 text-slate-500 ring-white/10 hover:text-slate-200"
                          }`}
                          aria-pressed={selectedDocs.has(doc.id)}
                          aria-label={`Toggle document ${doc.label}`}
                          title={doc.label}
                        >
                          {doc.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <p className="mt-2 text-xs text-amber-200/90" data-testid="no-documents-hint">
                  No documents uploaded yet. Upload files from the home page, or switch to General Agent.
                </p>
              )}
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-2 shadow-xl shadow-black/10 transition focus-within:border-cyan-400/20 focus-within:bg-white/[0.045]">
          <div className="flex items-end gap-2">
            <div className="relative flex-1">
              <textarea
                ref={textareaRef}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleKey}
                disabled={disabled && !isStreaming}
                rows={1}
                placeholder={mode === "documents" ? "Ask a question grounded in your knowledge…" : "Ask Cortexa anything…"}
                aria-label="Message input"
                data-testid="composer-input"
                className="w-full resize-none overflow-hidden bg-transparent px-3 py-2.5 text-sm leading-6 text-slate-100 placeholder:text-slate-600 outline-none disabled:cursor-not-allowed disabled:opacity-50"
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
                className="mb-0.5 shrink-0 rounded-xl border border-rose-400/20 bg-rose-500/10 px-4 py-2.5 text-sm font-medium text-rose-200 transition hover:bg-rose-500/15"
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
                className="mb-0.5 shrink-0 rounded-xl bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-600"
                data-testid="send-button"
                aria-label="Send message"
              >
                Send
              </button>
            )}
          </div>
        </div>

        {len > MAX_LENGTH * 0.8 && (
          <p
            className={`mt-1.5 text-right text-xs ${overLimit ? "text-rose-400" : "text-slate-600"}`}
            role={overLimit ? "alert" : undefined}
            data-testid="char-count"
          >
            {len.toLocaleString()} / {MAX_LENGTH.toLocaleString()}
          </p>
        )}
      </div>
    </section>
  );
}

function ScopeButton({
  active,
  onClick,
  children,
  testId,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  testId?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      data-testid={testId}
      className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
        active
          ? "bg-white/[0.08] text-white shadow-sm ring-1 ring-white/10"
          : "text-slate-500 hover:bg-white/[0.035] hover:text-slate-300"
      }`}
    >
      {children}
    </button>
  );
}
