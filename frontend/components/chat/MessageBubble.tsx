"use client";

import { useState, useCallback } from "react";

import type { ConversationMessage } from "@/types/api";
import { CitationCard } from "@/components/chat/CitationCard";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
import { ToolActivity } from "@/components/chat/ToolActivity";
import { removeMessageFeedback, submitMessageFeedback } from "@/services/conversations";
import type { MessageFeedback } from "@/types/api";

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
  const [feedback, setFeedback] = useState<MessageFeedback | null>(message.feedback ?? null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackReason, setFeedbackReason] = useState<
    "incorrect" | "missing_source" | "not_relevant" | "incomplete" | "unclear" | "other"
  >("incorrect");
  const [feedbackComment, setFeedbackComment] = useState("");
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);

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

  async function saveHelpful() {
    setFeedbackBusy(true);
    setFeedbackError(null);
    const result = await submitMessageFeedback(message.conversation_id, message.id, {
      sentiment: "helpful",
    });
    if (result.ok) {
      setFeedback(result.data);
      setFeedbackOpen(false);
    } else {
      setFeedbackError(result.error);
    }
    setFeedbackBusy(false);
  }

  async function saveNotHelpful() {
    setFeedbackBusy(true);
    setFeedbackError(null);
    const result = await submitMessageFeedback(message.conversation_id, message.id, {
      sentiment: "not_helpful",
      reason: feedbackReason,
      comment: feedbackComment.trim() || undefined,
    });
    if (result.ok) {
      setFeedback(result.data);
      setFeedbackOpen(false);
    } else {
      setFeedbackError(result.error);
    }
    setFeedbackBusy(false);
  }

  async function clearFeedback() {
    setFeedbackBusy(true);
    setFeedbackError(null);
    const result = await removeMessageFeedback(message.conversation_id, message.id);
    if (result.ok) {
      setFeedback(null);
      setFeedbackOpen(false);
      setFeedbackComment("");
    } else {
      setFeedbackError(result.error);
    }
    setFeedbackBusy(false);
  }

  return (
    <article
      className={`group flex w-full gap-3 ${isUser ? "justify-end" : "justify-start"}`}
      data-testid={`message-${message.id}`}
      aria-label={`${isUser ? "Your" : "Assistant"} message`}
    >
      {!isUser && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-cyan-400/15 bg-cyan-400/[0.07] text-[10px] font-bold text-cyan-200">
          AI
        </div>
      )}

      <div className={`flex max-w-[88%] flex-col gap-1.5 sm:max-w-[78%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-7 ${
            isUser
              ? "border border-cyan-400/15 bg-cyan-400/[0.07] text-slate-100"
              : "border border-white/[0.07] bg-white/[0.035] text-slate-200 shadow-sm shadow-black/10"
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
          <p className="px-1 text-[11px] text-slate-600" data-testid="message-metadata">
            {message.model}
            {message.latency_ms != null && ` · ${Math.round(message.latency_ms)}ms`}
          </p>
        )}

        {!isUser && !isStreaming && message.status === "complete" && (
          <div className="w-full" data-testid={`feedback-${message.id}`}>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-600">Quality feedback</span>
              <button
                type="button"
                onClick={() => void saveHelpful()}
                disabled={feedbackBusy}
                className={`rounded-md px-2 py-1 ring-1 transition ${
                  feedback?.sentiment === "helpful"
                    ? "bg-emerald-500/20 text-emerald-200 ring-emerald-400/40"
                    : "text-slate-400 ring-white/10 hover:text-emerald-200"
                }`}
                aria-label="Mark response helpful"
              >
                Helpful
              </button>
              <button
                type="button"
                onClick={() => setFeedbackOpen((value) => !value)}
                disabled={feedbackBusy}
                className={`rounded-md px-2 py-1 ring-1 transition ${
                  feedback?.sentiment === "not_helpful"
                    ? "bg-rose-500/20 text-rose-200 ring-rose-400/40"
                    : "text-slate-400 ring-white/10 hover:text-rose-200"
                }`}
                aria-label="Report response issue"
              >
                Not helpful
              </button>
              {feedback ? (
                <button type="button" onClick={() => void clearFeedback()} disabled={feedbackBusy} className="text-slate-500 hover:text-slate-300">
                  Remove
                </button>
              ) : null}
            </div>
            {feedbackOpen ? (
              <div className="mt-2 space-y-2 rounded-lg bg-slate-900/70 p-3 ring-1 ring-white/10">
                <label className="block text-xs text-slate-300">
                  What was wrong?
                  <select
                    value={feedbackReason}
                    onChange={(event) => setFeedbackReason(event.target.value as typeof feedbackReason)}
                    className="mt-1 w-full rounded-md bg-slate-950 px-2 py-2 text-sm text-slate-200 ring-1 ring-white/10"
                  >
                    <option value="incorrect">Incorrect answer</option>
                    <option value="missing_source">Missing or wrong source</option>
                    <option value="not_relevant">Not relevant</option>
                    <option value="incomplete">Incomplete</option>
                    <option value="unclear">Unclear</option>
                    <option value="other">Other</option>
                  </select>
                </label>
                <textarea
                  value={feedbackComment}
                  onChange={(event) => setFeedbackComment(event.target.value)}
                  maxLength={1000}
                  placeholder="Optional details for the review team"
                  className="min-h-20 w-full rounded-md bg-slate-950 px-2 py-2 text-sm text-slate-200 ring-1 ring-white/10"
                />
                <div className="flex justify-end gap-2">
                  <button type="button" onClick={() => setFeedbackOpen(false)} className="rounded-md px-3 py-1.5 text-xs text-slate-400">Cancel</button>
                  <button type="button" onClick={() => void saveNotHelpful()} disabled={feedbackBusy} className="rounded-md bg-rose-500/20 px-3 py-1.5 text-xs text-rose-100 ring-1 ring-rose-400/30">
                    {feedbackBusy ? "Saving…" : "Submit feedback"}
                  </button>
                </div>
              </div>
            ) : null}
            {feedbackError ? <p className="mt-1 text-xs text-rose-300">{feedbackError}</p> : null}
            {feedback ? <p className="mt-1 text-xs text-slate-500">Feedback saved · {feedback.status}</p> : null}
          </div>
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
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.045] text-[10px] font-semibold text-slate-400">
          U
        </div>
      )}
    </article>
  );
}
