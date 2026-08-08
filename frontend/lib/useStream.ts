/**
 * useStream — React hook that manages a single fetch-based SSE stream.
 *
 * Streaming contract:
 * - Canonical assistant text event is `delta`. Append only `delta` content.
 * - Legacy `assistant_token` is ignored for the text buffer (same payload used
 *   to be dual-emitted and caused duplicated answers).
 * - `complete` finalizes the turn; duplicate complete/error events are ignored.
 * - `error` / `agent_failed` only surface a terminal failure (nested or flat
 *   `{code,message}` shapes are accepted).
 */
"use client";

import { useCallback, useRef, useState } from "react";
import type {
  SSEEvent,
  SSECompleteData,
  SSEMetadataData,
  SSEProgressData,
  SSEStartData,
  SSEToolCallArgumentsData,
  SSEToolCallStartedData,
  SSEToolExecutionFailedData,
  SSEToolExecutionStartedData,
  SSEToolExecutionSucceededData,
} from "@/types/api";
import type { AgentLifecycleEventData, AgentLifecycleEventName } from "@/types/agents";

export type StreamCallbacks = {
  onStart?: (data: SSEStartData) => void;
  onDelta: (content: string) => void;
  onCitation: (citation: SSEEvent & { event: "citation" }) => void;
  onComplete: (data: SSECompleteData) => void;
  onMetadata?: (data: SSEMetadataData) => void;
  onProgress?: (data: SSEProgressData) => void;
  onError: (message: string) => void;
  onToolCallStarted?: (data: SSEToolCallStartedData) => void;
  onToolCallArguments?: (data: SSEToolCallArgumentsData) => void;
  onToolExecutionStarted?: (data: SSEToolExecutionStartedData) => void;
  onToolExecutionSucceeded?: (data: SSEToolExecutionSucceededData) => void;
  onToolExecutionFailed?: (data: SSEToolExecutionFailedData) => void;
  onMemoryEvent?: (event: SSEEvent) => void;
  onAgentEvent?: (event: { event: AgentLifecycleEventName; data: AgentLifecycleEventData }) => void;
};

type StreamState = "idle" | "streaming" | "done" | "error";

function extractErrorMessage(data: unknown): string {
  if (!data || typeof data !== "object") return "Streaming failed";
  const record = data as Record<string, unknown>;
  const nested = record.error;
  if (nested && typeof nested === "object") {
    const message = (nested as Record<string, unknown>).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  if (typeof record.message === "string" && record.message.trim()) {
    return record.message;
  }
  return "Streaming failed";
}

export function useStream() {
  const abortRef = useRef<AbortController | null>(null);
  const terminalRef = useRef<"none" | "complete" | "error">("none");
  const [state, setState] = useState<StreamState>("idle");

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState((s) => (s === "streaming" ? "idle" : s));
  }, []);

  const run = useCallback(
    async (
      generatorFn: (signal: AbortSignal) => AsyncGenerator<SSEEvent>,
      callbacks: StreamCallbacks,
    ) => {
      // Cancel any in-flight stream first.
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      terminalRef.current = "none";
      setState("streaming");

      try {
        for await (const event of generatorFn(controller.signal)) {
          if (controller.signal.aborted) break;

          switch (event.event) {
            case "start":
              callbacks.onStart?.(event.data);
              break;
            case "delta":
              // Canonical assistant text — append once.
              callbacks.onDelta(event.data.content);
              break;
            case "assistant_token":
              // Legacy alias — intentionally ignored to prevent duplicated text.
              break;
            case "citation":
              try {
                callbacks.onCitation(event as SSEEvent & { event: "citation" });
              } catch {
                // Recoverable citation UI failure must not fail the answer.
              }
              break;
            case "progress":
              callbacks.onProgress?.(event.data);
              break;
            case "metadata":
              callbacks.onMetadata?.(event.data);
              break;
            case "complete":
              if (terminalRef.current !== "none") break;
              terminalRef.current = "complete";
              callbacks.onComplete(event.data);
              setState("done");
              break;
            case "error":
            case "agent_failed": {
              if (terminalRef.current === "complete") {
                // Never demote a successful complete into a terminal error toast.
                break;
              }
              if (terminalRef.current === "error") break;
              terminalRef.current = "error";
              callbacks.onError(extractErrorMessage(event.data));
              setState("error");
              break;
            }
            case "tool_call_started":
              callbacks.onToolCallStarted?.(event.data);
              break;
            case "tool_call_arguments":
              callbacks.onToolCallArguments?.(event.data);
              break;
            case "tool_execution_started":
              callbacks.onToolExecutionStarted?.(event.data);
              break;
            case "tool_execution_succeeded":
              callbacks.onToolExecutionSucceeded?.(event.data);
              break;
            case "tool_execution_failed":
              callbacks.onToolExecutionFailed?.(event.data);
              break;
            case "memory_retrieval_started":
            case "memory_retrieval_completed":
            case "memory_candidate_proposed":
            case "memory_saved":
            case "memory_updated":
            case "memory_archived":
            case "memory_deleted":
            case "memory_action_failed":
              callbacks.onMemoryEvent?.(event);
              break;
            case "agent_started":
              // Keep existing start IDs; only signal that the agent loop began.
              break;
            case "run_started":
            case "complexity_classified":
            case "planning_started":
            case "plan_created":
            case "safety_checked":
            case "task_ready":
            case "task_started":
            case "task_completed":
            case "task_failed":
            case "task_skipped":
            case "handoff":
            case "approval_required":
            case "approval_resolved":
            case "run_cancelled":
            case "run_completed":
            case "run_failed":
            case "run_timed_out":
              callbacks.onAgentEvent?.(event);
              break;
            default:
              break;
          }
        }
        // If we never received `complete`, e.g. stream was aborted silently.
        setState((s) => (s === "streaming" ? "idle" : s));
      } catch (err) {
        if (controller.signal.aborted) {
          setState("idle");
          return;
        }
        if (terminalRef.current === "complete") {
          setState("done");
          return;
        }
        if (terminalRef.current !== "error") {
          terminalRef.current = "error";
          callbacks.onError(err instanceof Error ? err.message : "Streaming failed");
        }
        setState("error");
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
      }
    },
    [],
  );

  return { state, run, cancel, isStreaming: state === "streaming" };
}
