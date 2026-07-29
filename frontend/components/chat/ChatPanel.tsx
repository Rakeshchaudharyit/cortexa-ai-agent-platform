"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  editMessage,
  getConversation,
  regenerate,
  streamMessage,
} from "@/services/conversations";
import { useStream } from "@/lib/useStream";
import type { ConversationMessage, MessageCitation } from "@/types/api";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { MessageList } from "@/components/chat/MessageList";

type StreamingState = {
  content: string;
  citations: MessageCitation[];
  userMessageId: string | null;
  assistantMessageId: string | null;
};

type Props = {
  conversationId: string;
};

export function ChatPanel({ conversationId }: Props) {
  const router = useRouter();
  const { run, cancel, isStreaming } = useStream();
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [streaming, setStreaming] = useState<StreamingState | null>(null);

  // Track current conversation to cancel stream on switch.
  const convIdRef = useRef(conversationId);
  useEffect(() => {
    convIdRef.current = conversationId;
  }, [conversationId]);

  const loadConversation = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    setMessages([]);
    setStreaming(null);
    cancel();

    const result = await getConversation(id);
    setLoading(false);

    if (!result.ok) {
      if (result.status === 404) {
        router.push("/chat");
        return;
      }
      setError(result.error);
      return;
    }

    setMessages(result.data.messages.filter((m) => m.is_active));
  }, [cancel, router]);

  useEffect(() => {
    void loadConversation(conversationId);
  }, [conversationId, loadConversation]);

  async function handleSend(content: string, documentIds: string[] | null) {
    const id = conversationId;

    // Optimistically show user message.
    const tempUserMsg: ConversationMessage = {
      id: `temp-user-${Date.now()}`,
      conversation_id: id,
      role: "user",
      content,
      status: "complete",
      sequence_number: messages.length + 1,
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
      citations: [],
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    setStreaming({ content: "", citations: [], userMessageId: null, assistantMessageId: null });

    await run(
      (signal) =>
        streamMessage(
          id,
          { content, document_ids: documentIds },
          signal,
        ),
      {
        onDelta: (delta) => {
          setStreaming((prev) =>
            prev ? { ...prev, content: prev.content + delta } : null,
          );
        },
        onCitation: (event) => {
          setStreaming((prev) =>
            prev
              ? { ...prev, citations: [...prev.citations, event.data.citation] }
              : null,
          );
        },
        onComplete: (data) => {
          // Replace temp user message + insert real messages.
          setMessages((prev) => {
            const without = prev.filter((m) => !m.id.startsWith("temp-user-"));
            // Check if we already have these messages.
            const hasUser = without.some((m) => m.id === data.message.id);
            // data.message is the assistant message from "complete" event.
            return [...without, ...(hasUser ? [] : [data.message])];
          });
          setStreaming(null);
          // Reload full conversation to get both messages with correct IDs.
          void loadConversation(id);
        },
        onMetadata: () => {
          // Optionally store latency/model info.
        },
        onError: (msg) => {
          setStreaming(null);
          setError(msg);
          // Remove temp user message on error.
          setMessages((prev) => prev.filter((m) => !m.id.startsWith("temp-user-")));
        },
      },
    );
  }

  async function handleEdit(messageId: string, content: string) {
    const result = await editMessage(conversationId, messageId, content);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    // Reload to get refreshed state.
    await loadConversation(conversationId);
  }

  async function handleRegenerate() {
    const result = await regenerate(conversationId, {});
    if (!result.ok) {
      setError(result.error);
      return;
    }
    await loadConversation(conversationId);
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden" data-testid="chat-panel">
      {/* Error banner */}
      {error && (
        <div
          className="flex items-center justify-between border-b border-rose-500/20 bg-rose-500/10 px-4 py-2"
          role="alert"
          data-testid="chat-error-banner"
        >
          <p className="text-sm text-rose-200">{error}</p>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-xs text-rose-400 hover:text-rose-200 transition ml-4"
            aria-label="Dismiss error"
          >
            ✕
          </button>
        </div>
      )}

      {/* Message history */}
      <MessageList
        messages={messages}
        streaming={streaming}
        onEdit={handleEdit}
        onRegenerate={handleRegenerate}
        loading={loading}
        error={null}
      />

      {/* Composer */}
      <ChatComposer
        disabled={loading}
        isStreaming={isStreaming}
        onSend={(content, docIds) => void handleSend(content, docIds)}
        onCancel={cancel}
      />
    </div>
  );
}
