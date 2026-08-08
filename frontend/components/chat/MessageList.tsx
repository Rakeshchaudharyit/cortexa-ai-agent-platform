"use client";

import { useEffect, useRef } from "react";
import type { ConversationMessage, MessageCitation, ToolActivityItem } from "@/types/api";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { ToolActivity } from "@/components/chat/ToolActivity";

export type StreamingState = {
  content: string;
  citations: MessageCitation[];
  userMessageId: string | null;
  assistantMessageId: string | null;
  toolActivity: ToolActivityItem[];
  statusLabel: string | null;
};

type Props = {
  messages: ConversationMessage[];
  streaming: StreamingState | null;
  onEdit?: (messageId: string, content: string) => void;
  onRegenerate?: () => void;
  loading?: boolean;
  error?: string | null;
};

export function MessageList({
  messages,
  streaming,
  onEdit,
  onRegenerate,
  loading,
  error,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof bottomRef.current?.scrollIntoView === "function") {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages.length, streaming?.content, streaming?.toolActivity?.length, streaming?.statusLabel]);

  const userMessages = messages.filter((m) => m.role === "user" && m.is_active);
  const assistantMessages = messages.filter((m) => m.role === "assistant" && m.is_active);
  const latestUserMsgId = userMessages.at(-1)?.id;
  const latestAssistantMsgId = assistantMessages.at(-1)?.id;

  const showPreparing = Boolean(streaming) && !streaming!.content && streaming!.toolActivity.length === 0;
  const showStreamingBubble = Boolean(streaming && streaming.content);

  const streamingMsg: ConversationMessage | null =
    streaming && showStreamingBubble
      ? {
          id: streaming.assistantMessageId || "streaming-assistant",
          conversation_id: "",
          role: "assistant",
          content: streaming.content,
          status: "streaming",
          sequence_number: 0,
          is_active: true,
          grounded: null,
          model: null,
          provider: null,
          prompt_tokens: null,
          completion_tokens: null,
          total_tokens: null,
          latency_ms: null,
          finish_reason: null,
          error_code: null,
          regenerated_from_message_id: null,
          edited_from_message_id: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          citations: streaming.citations,
          tool_executions: [],
        }
      : null;

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center px-6" data-testid="messages-loading">
        <div className="flex items-center gap-3 rounded-2xl border border-white/[0.07] bg-white/[0.025] px-5 py-4 text-sm text-slate-400">
          <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-400" />
          Loading conversation…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center px-8" data-testid="messages-error">
        <div className="max-w-md rounded-2xl border border-rose-400/15 bg-rose-500/[0.07] px-5 py-4 text-center">
          <p className="text-sm text-rose-200">{error}</p>
        </div>
      </div>
    );
  }

  if (messages.length === 0 && !streaming) {
    return (
      <div className="flex flex-1 items-center justify-center overflow-y-auto px-6 py-10" data-testid="messages-empty">
        <div className="max-w-2xl text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.07] text-sm font-bold text-cyan-200">AI</div>
          <h2 className="mt-5 text-xl font-semibold text-white">Start with a question</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">
            Use General Agent for broad assistance, or Document Knowledge for grounded responses from your governed sources.
          </p>
          <div className="mt-6 grid gap-2 text-left sm:grid-cols-2">
            <div className="cx-panel-soft p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-cyan-300/75">Document Knowledge</p>
              <p className="mt-2 text-sm text-slate-300">“Summarize the architecture and cite the source.”</p>
            </div>
            <div className="cx-panel-soft p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-violet-300/75">General Agent</p>
              <p className="mt-2 text-sm text-slate-300">“Turn these requirements into an implementation plan.”</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex flex-1 flex-col gap-5 overflow-y-auto px-4 py-5 sm:px-6 lg:px-8"
      role="log"
      aria-label="Message history"
      aria-live="polite"
      data-testid="message-list"
    >
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-5">
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onEdit={msg.id === latestUserMsgId && onEdit ? (content) => onEdit(msg.id, content) : undefined}
            onRegenerate={msg.id === latestAssistantMsgId ? onRegenerate : undefined}
          />
        ))}

        {streaming && streaming.toolActivity.length > 0 && (
          <div className="max-w-[88%] sm:max-w-[78%]">
            <ToolActivity items={streaming.toolActivity} />
          </div>
        )}

        {showPreparing && (
          <div
            className="flex w-fit max-w-[88%] items-center gap-3 rounded-2xl border border-white/[0.07] bg-white/[0.035] px-4 py-3 text-sm text-slate-300 shadow-sm shadow-black/10"
            data-testid="preparing-response"
            aria-live="polite"
          >
            <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-400" />
            {streaming?.statusLabel || "Preparing response…"}
          </div>
        )}

        {streamingMsg && <MessageBubble key="streaming" message={streamingMsg} isStreaming />}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
