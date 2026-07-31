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
import type { ConversationMessage, MessageCitation, ToolActivityItem } from "@/types/api";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { MessageList } from "@/components/chat/MessageList";

type StreamingState = {
  content: string;
  citations: MessageCitation[];
  userMessageId: string | null;
  assistantMessageId: string | null;
  toolActivity: ToolActivityItem[];
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
      tool_executions: [],
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    setStreaming({
      content: "",
      citations: [],
      userMessageId: null,
      assistantMessageId: null,
      toolActivity: [],
    });

    await run(
      (signal) =>
        streamMessage(
          id,
          { content, document_ids: documentIds },
          signal,
        ),
      {
        onStart: (data) => {
          setStreaming((prev) =>
            prev
              ? {
                  ...prev,
                  userMessageId: data.user_message_id,
                  assistantMessageId: data.assistant_message_id,
                }
              : null,
          );
        },
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
        onToolCallStarted: (data) => {
          setStreaming((prev) => {
            if (!prev) return prev;
            const existing = prev.toolActivity.find((t) => t.id === data.tool_call_id);
            if (existing) return prev;
            return {
              ...prev,
              toolActivity: [
                ...prev.toolActivity,
                {
                  id: data.tool_call_id,
                  tool_name: data.tool_name,
                  status: "started",
                },
              ],
            };
          });
        },
        onToolCallArguments: (data) => {
          setStreaming((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              toolActivity: prev.toolActivity.map((item) =>
                item.id === data.tool_call_id
                  ? { ...item, arguments: data.arguments }
                  : item,
              ),
            };
          });
        },
        onToolExecutionStarted: (data) => {
          setStreaming((prev) => {
            if (!prev) return prev;
            const byCall = prev.toolActivity.find((t) => t.id === data.tool_call_id);
            if (byCall) {
              return {
                ...prev,
                toolActivity: prev.toolActivity.map((item) =>
                  item.id === data.tool_call_id
                    ? {
                        ...item,
                        status: "running",
                        execution_id: data.execution_id,
                      }
                    : item,
                ),
              };
            }
            return {
              ...prev,
              toolActivity: [
                ...prev.toolActivity,
                {
                  id: data.execution_id,
                  tool_name: data.tool_name,
                  status: "running",
                  execution_id: data.execution_id,
                },
              ],
            };
          });
        },
        onToolExecutionSucceeded: (data) => {
          setStreaming((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              toolActivity: prev.toolActivity.map((item) =>
                item.id === data.tool_call_id || item.execution_id === data.execution_id
                  ? {
                      ...item,
                      status: "succeeded",
                      result: data.result,
                      execution_id: data.execution_id,
                    }
                  : item,
              ),
            };
          });
        },
        onToolExecutionFailed: (data) => {
          setStreaming((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              toolActivity: prev.toolActivity.map((item) =>
                item.id === data.tool_call_id || item.execution_id === data.execution_id
                  ? {
                      ...item,
                      status: "failed",
                      error_message: data.error_message,
                      execution_id: data.execution_id,
                    }
                  : item,
              ),
            };
          });
        },
        onComplete: () => {
          setStreaming(null);
          void loadConversation(id);
        },
        onMetadata: () => {
          // Optionally store latency/model info.
        },
        onError: (msg) => {
          setStreaming(null);
          setError(msg);
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

      <MessageList
        messages={messages}
        streaming={streaming}
        onEdit={handleEdit}
        onRegenerate={handleRegenerate}
        loading={loading}
      />

      <ChatComposer
        onSend={handleSend}
        isStreaming={isStreaming}
        onCancel={cancel}
      />
    </div>
  );
}
