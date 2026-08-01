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
  /** Shown before the first model token arrives. */
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

  const showPreparing =
    Boolean(streaming) &&
    !streaming!.content &&
    streaming!.toolActivity.length === 0;

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
      <div className="flex flex-1 items-center justify-center" data-testid="messages-loading">
        <p className="text-sm text-slate-400">Loading conversation…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center px-8" data-testid="messages-error">
        <p className="text-sm text-rose-300">{error}</p>
      </div>
    );
  }

  if (messages.length === 0 && !streaming) {
    return (
      <div
        className="flex flex-1 flex-col items-center justify-center gap-3 text-center px-8"
        data-testid="messages-empty"
      >
        <p className="text-2xl">💬</p>
        <p className="text-sm text-slate-400">Start the conversation below.</p>
      </div>
    );
  }

  return (
    <div
      className="flex flex-1 flex-col gap-4 overflow-y-auto px-6 py-4"
      role="log"
      aria-label="Message history"
      aria-live="polite"
      data-testid="message-list"
    >
      {messages.map((msg) => (
        <MessageBubble
          key={msg.id}
          message={msg}
          onEdit={
            msg.id === latestUserMsgId && onEdit
              ? (content) => onEdit(msg.id, content)
              : undefined
          }
          onRegenerate={msg.id === latestAssistantMsgId ? onRegenerate : undefined}
        />
      ))}

      {streaming && streaming.toolActivity.length > 0 && (
        <div className="max-w-[80%]">
          <ToolActivity items={streaming.toolActivity} />
        </div>
      )}

      {showPreparing && (
        <div
          className="flex max-w-[80%] items-center gap-2 rounded-2xl bg-slate-800/60 px-4 py-2.5 text-sm text-slate-300 ring-1 ring-white/10"
          data-testid="preparing-response"
          aria-live="polite"
        >
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-cyan-400" />
          {streaming?.statusLabel || "Preparing response…"}
        </div>
      )}

      {streamingMsg && (
        <MessageBubble key="streaming" message={streamingMsg} isStreaming />
      )}

      <div ref={bottomRef} />
    </div>
  );
}
