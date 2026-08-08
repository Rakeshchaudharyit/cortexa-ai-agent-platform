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
import { AgentRunActivity } from "@/components/agents/AgentRunActivity";
import { CancelRunDialog } from "@/components/agents/CancelRunDialog";
import { cancelAgentRun } from "@/services/agents";
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
  const [agentRunId, setAgentRunId] = useState<string | null>(null);
  const [agentRevision, setAgentRevision] = useState(0);
  const [agentStatusText, setAgentStatusText] = useState<string | null>(null);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [cancellingRun, setCancellingRun] = useState(false);

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
    if (!opts?.quiet) {
      setAgentRunId(null);
      setAgentStatusText(null);
    }
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
    const persistedRunId =
      result.data.active_agent_run_id ??
      [...result.data.messages]
        .reverse()
        .find((message) => message.role === "assistant" && message.agent_run_id)?.agent_run_id;
    if (persistedRunId) {
      setAgentRunId(persistedRunId);
      setAgentRevision((value) => value + 1);
    } else if (!opts?.quiet) {
      setAgentRunId(null);
      setAgentStatusText(null);
    }
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
    setAgentRunId(null);
    setAgentStatusText(null);

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
        onAgentEvent: (event) => {
          const runId = event.data.agent_run_id || event.data.run_id;
          if (runId) setAgentRunId(runId);
          const labels: Record<string, string> = {
            run_started: "Preparing a coordinated response…",
            planning_started: "Planning the work…",
            plan_created: `Plan ready${event.data.task_count ? ` · ${event.data.task_count} tasks` : ""}`,
            task_started: "Specialist agents are working…",
            approval_required: "Your approval is required to continue.",
            approval_resolved: "Resuming coordinated work…",
            run_completed: "Coordinated response complete",
            run_cancelled: "Coordinated response cancelled",
            run_failed: "Coordinated response could not be completed",
            run_timed_out: "Coordinated response timed out",
          };
          const statusText = labels[event.event];
          if (statusText) setAgentStatusText(statusText);
          setAgentRevision((value) => value + 1);
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
        onMetadata: (data) => {
          if (data.agent_run_id) {
            setAgentRunId(data.agent_run_id);
            setAgentRevision((value) => value + 1);
          }
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
    if (agentRunId) {
      setCancelDialogOpen(true);
      return;
    }
    cancel();
    setStreaming(null);
    setError("Response stopped");
  }

  async function confirmAgentCancellation() {
    if (!agentRunId || cancellingRun) return;
    setCancellingRun(true);
    setAgentStatusText("Cancelling coordinated response…");
    // Stop the browser stream immediately so the UI responds without waiting
    // for the cancellation endpoint or the local model to unwind.
    cancel();
    setStreaming(null);
    const result = await cancelAgentRun(agentRunId);
    setCancellingRun(false);
    setCancelDialogOpen(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setAgentStatusText("Coordinated response cancelled");
    setAgentRevision((value) => value + 1);
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
    <div className="flex flex-1 flex-col overflow-hidden bg-[radial-gradient(circle_at_50%_-10%,rgba(34,211,238,0.035),transparent_32%)]" data-testid="chat-panel">
      {error && (
        <div
          className="mx-4 mt-3 flex items-center justify-between rounded-xl border border-rose-400/15 bg-rose-500/[0.07] px-4 py-3 sm:mx-6"
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
        className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] bg-white/[0.012] px-4 py-2.5 sm:px-6"
        data-testid="chat-memory-controls"
      >
        <MemoryActivity activity={memoryActivity} />
        <label className="flex items-center gap-2 text-xs text-slate-400">
          <span>Conversation memory</span>
          <input
            type="checkbox"
            checked={memoryEnabled !== false}
            data-testid="conversation-memory-toggle"
            onChange={(e) => void handleMemoryToggle(e.target.checked)}
          />
        </label>
      </div>

      <AgentRunActivity
        runId={agentRunId}
        revision={agentRevision}
        statusText={agentStatusText}
      />

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
      <CancelRunDialog
        open={cancelDialogOpen}
        busy={cancellingRun}
        onCancel={() => setCancelDialogOpen(false)}
        onConfirm={() => void confirmAgentCancellation()}
      />
    </div>
  );
}
