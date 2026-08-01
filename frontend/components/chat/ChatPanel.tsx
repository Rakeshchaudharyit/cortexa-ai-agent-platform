"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  editMessage,
  getConversation,
  regenerate,
  streamMessage,
} from "@/services/conversations";
import { listDocuments } from "@/services/documents";
import { updateConversationMemory } from "@/services/memories";
import { useStream } from "@/lib/useStream";
import type { ConversationMessage, MessageCitation, ToolActivityItem } from "@/types/api";
import { ChatComposer, type ComposerDocument } from "@/components/chat/ChatComposer";
import { MessageList } from "@/components/chat/MessageList";
import { normalizeCitation } from "@/components/chat/CitationCard";
import {
  MemoryActivity,
  type MemoryActivityState,
} from "@/components/memory/MemoryActivity";

type StreamingState = {
  content: string;
  citations: MessageCitation[];
  userMessageId: string | null;
  assistantMessageId: string | null;
  toolActivity: ToolActivityItem[];
  /** Shown before the first model token arrives. */
  statusLabel: string | null;
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
  const [availableDocuments, setAvailableDocuments] = useState<ComposerDocument[]>([]);
  const [memoryActivity, setMemoryActivity] = useState<MemoryActivityState>({});
  const [memoryEnabled, setMemoryEnabled] = useState<boolean | null>(null);

  // Track current conversation to cancel stream on switch.
  const convIdRef = useRef(conversationId);
  useEffect(() => {
    convIdRef.current = conversationId;
  }, [conversationId]);

  const loadConversation = useCallback(async (id: string, opts?: { preserveStream?: boolean; quiet?: boolean }) => {
    if (!opts?.quiet) {
      setLoading(true);
      setMessages([]);
    }
    setError(null);
    if (!opts?.preserveStream) {
      setStreaming(null);
      cancel();
    } else {
      setStreaming(null);
    }
    if (!opts?.quiet) {
      setMemoryActivity({});
    }

    const result = await getConversation(id);
    if (!opts?.quiet) {
      setLoading(false);
    }

    if (!result.ok) {
      if (result.status === 404) {
        router.push("/chat");
        return;
      }
      // After a successful stream, a reload failure must not look like a generation failure.
      if (!opts?.quiet) {
        setError(result.error);
      }
      return;
    }

    setMessages(result.data.messages.filter((m) => m.is_active));
    setMemoryEnabled(result.data.memory_enabled ?? null);
    setMemoryActivity({
      enabled: result.data.memory_enabled !== false,
    });
  }, [cancel, router]);

  useEffect(() => {
    void loadConversation(conversationId);
  }, [conversationId, loadConversation]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const result = await listDocuments();
      if (cancelled || !result.ok) return;
      setAvailableDocuments(
        result.data.items
          .filter((doc) => doc.status === "ready")
          .map((doc) => ({
            id: doc.id,
            label: doc.original_filename,
          })),
      );
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSend(content: string, documentIds: string[] | null) {
    const id = conversationId;
    setError(null);

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
      statusLabel: "Preparing your question…",
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
          setMessages((prev) =>
            prev.map((m) =>
              m.id.startsWith("temp-user-")
                ? { ...m, id: data.user_message_id }
                : m,
            ),
          );
          setStreaming((prev) =>
            prev
              ? {
                  ...prev,
                  userMessageId: data.user_message_id,
                  assistantMessageId: data.assistant_message_id,
                  statusLabel: prev.content
                    ? null
                    : prev.statusLabel || "Connecting to local model…",
                }
              : null,
          );
        },
        onDelta: (delta) => {
          setStreaming((prev) =>
            prev
              ? {
                  ...prev,
                  content: prev.content + delta,
                  statusLabel: null,
                }
              : null,
          );
        },
        onCitation: (event) => {
          const normalized = normalizeCitation(
            event.data.citation as MessageCitation & Record<string, unknown>,
          );
          if (!normalized) return;
          setStreaming((prev) => {
            if (!prev) return prev;
            if (prev.citations.some((c) => c.citation_index === normalized.citation_index)) {
              return prev;
            }
            return { ...prev, citations: [...prev.citations, normalized] };
          });
        },
        onProgress: (data) => {
          setStreaming((prev) => {
            if (!prev || prev.content) return prev;
            return { ...prev, statusLabel: data.message || prev.statusLabel };
          });
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
        onMemoryEvent: (event) => {
          if (event.event === "memory_retrieval_started") {
            setMemoryActivity((prev) => ({ ...prev, retrieving: true }));
          } else if (event.event === "memory_retrieval_completed") {
            setMemoryActivity((prev) => ({
              ...prev,
              retrieving: false,
              count: event.data.count,
              references: event.data.references,
              enabled: true,
            }));
          } else if (event.event === "memory_candidate_proposed") {
            setMemoryActivity((prev) => ({
              ...prev,
              proposed: {
                title: event.data.title,
                category: event.data.category,
                reason: event.data.reason,
              },
            }));
          } else if (event.event === "memory_saved") {
            setMemoryActivity((prev) => ({
              ...prev,
              savedMessage: event.data.title
                ? `Preference saved: ${event.data.title}`
                : "Preference saved",
              proposed: null,
            }));
          } else if (event.event === "memory_archived") {
            const titles = event.data.titles?.join(", ");
            setMemoryActivity((prev) => ({
              ...prev,
              forgottenMessage: titles ? `Memory removed: ${titles}` : "Memory removed",
            }));
          } else if (event.event === "memory_updated") {
            if (event.data.action === "disabled_for_conversation") {
              setMemoryEnabled(false);
              setMemoryActivity({ enabled: false });
            }
          } else if (event.event === "memory_action_failed") {
            setMemoryActivity((prev) => ({
              ...prev,
              failedMessage: event.data.message || "Memory action failed",
            }));
          }
        },
        onComplete: (data) => {
          setStreaming(null);
          setError(null);
          if (data?.message) {
            setMessages((prev) => {
              const withoutDupAssistant = prev.filter((m) => m.id !== data.message.id);
              return [...withoutDupAssistant, data.message];
            });
          }
          void loadConversation(id, { preserveStream: true, quiet: true });
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

  function handleCancel() {
    cancel();
    setStreaming(null);
    setError("Response stopped");
  }

  async function handleMemoryToggle(next: boolean) {
    const result = await updateConversationMemory(conversationId, next);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setMemoryEnabled(next);
    setMemoryActivity({ enabled: next });
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

      <div
        className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 px-4 py-2"
        data-testid="chat-memory-controls"
      >
        <MemoryActivity activity={memoryActivity} />
        <label className="flex items-center gap-2 text-xs text-slate-400">
          <span>Use memory</span>
          <input
            type="checkbox"
            checked={memoryEnabled !== false}
            data-testid="conversation-memory-toggle"
            onChange={(e) => void handleMemoryToggle(e.target.checked)}
          />
        </label>
      </div>

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
        onCancel={handleCancel}
        availableDocuments={availableDocuments}
      />
    </div>
  );
}
