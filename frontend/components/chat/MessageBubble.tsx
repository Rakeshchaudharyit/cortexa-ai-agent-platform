"use client";

import { useState, useCallback } from "react";

import type { ConversationMessage } from "@/types/api";
import { CitationCard } from "@/components/chat/CitationCard";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
import { ToolActivity } from "@/components/chat/ToolActivity";

type Props = {
  message: ConversationMessage;
  isStreaming?: boolean;
  /** Only shown for the latest user message */
  onEdit?: (content: string) => void;
  /** Only shown on the latest assistant message */
  onRegenerate?: () => void;
};

export function MessageBubble({ message, isStreaming, onEdit, onRegenerate }: Props) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editDraft, setEditDraft] = useState(message.content);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [message.content]);

  function handleEditSubmit() {
    if (editDraft.trim() && onEdit) {
      onEdit(editDraft.trim());
    }
    setEditing(false);
  }

  return (
    <article
      className={`group flex w-full gap-3 ${isUser ? "justify-end" : "justify-start"}`}
      data-testid={`message-${message.id}`}
      aria-label={`${isUser ? "Your" : "Assistant"} message`}
    >
      {!isUser && (
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-cyan-500/20 text-xs text-cyan-300 ring-1 ring-cyan-400/25">
          AI
        </div>
      )}

      <div className={`flex max-w-[80%] flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? "bg-cyan-500/15 text-slate-100 ring-1 ring-cyan-400/20"
              : "bg-slate-800/60 text-slate-200 ring-1 ring-white/10"
          }`}
        >
          {isUser ? (
            editing ? (
              <div className="flex flex-col gap-2">
                <textarea
                  value={editDraft}
                  onChange={(e) => setEditDraft(e.target.value)}
                  className="min-h-[4rem] w-full resize-y rounded-lg bg-slate-900/60 px-3 py-2 text-sm text-slate-100 outline-none ring-1 ring-cyan-400/40"
                  aria-label="Edit message"
                  data-testid="edit-textarea"
                  autoFocus
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleEditSubmit}
                    className="rounded px-2 py-1 text-xs bg-cyan-500/20 text-cyan-200 hover:bg-cyan-500/30 transition"
                    data-testid="edit-submit"
                  >
                    Save &amp; resend
                  </button>
                  <button
                    type="button"
                    onClick={() => { setEditing(false); setEditDraft(message.content); }}
                    className="rounded px-2 py-1 text-xs text-slate-400 hover:text-slate-200 transition"
                    data-testid="edit-cancel"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <p className="whitespace-pre-wrap">{message.content}</p>
            )
          ) : (
            <>
              <MarkdownContent content={message.content} />
              {isStreaming && (
                <span
                  className="inline-block h-4 w-0.5 animate-pulse bg-cyan-400 align-middle ml-0.5"
                  aria-label="Streaming"
                />
              )}
            </>
          )}
        </div>

        {/* Tool activity restored from history */}
        {!isUser && (message.tool_executions?.length ?? 0) > 0 && (
          <div className="w-full">
            <ToolActivity items={message.tool_executions ?? []} />
          </div>
        )}

        {/* Citations */}
        {!isUser && message.citations.length > 0 && (
          <div className="w-full space-y-1" data-testid="citations-list">
            {message.citations.map((c, idx) => (
              <CitationCard
                key={c.id || `${c.citation_index ?? idx}-${c.filename ?? "src"}`}
                citation={c}
              />
            ))}
          </div>
        )}

        {/* Metadata line */}
        {!isUser && message.model && !isStreaming && (
          <p className="text-xs text-slate-600" data-testid="message-metadata">
            {message.model}
            {message.latency_ms != null && ` · ${Math.round(message.latency_ms)}ms`}
          </p>
        )}

        {/* Actions */}
        <div
          className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition"
          aria-label="Message actions"
        >
          {!isUser && !isStreaming && (
            <button
              type="button"
              onClick={() => void handleCopy()}
              className="rounded px-2 py-0.5 text-xs text-slate-500 hover:text-slate-300 transition"
              aria-label="Copy response"
              data-testid="copy-button"
            >
              {copied ? "Copied!" : "Copy"}
            </button>
          )}
          {!isUser && !isStreaming && onRegenerate && (
            <button
              type="button"
              onClick={onRegenerate}
              className="rounded px-2 py-0.5 text-xs text-slate-500 hover:text-slate-300 transition"
              aria-label="Regenerate response"
              data-testid="regenerate-button"
            >
              Regenerate
            </button>
          )}
          {isUser && !editing && onEdit && (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded px-2 py-0.5 text-xs text-slate-500 hover:text-slate-300 transition"
              aria-label="Edit message"
              data-testid="edit-button"
            >
              Edit
            </button>
          )}
        </div>
      </div>

      {isUser && (
        <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-700/60 text-xs text-slate-300 ring-1 ring-white/10">
          U
        </div>
      )}
    </article>
  );
}
