/**
 * useStream — React hook that manages a single fetch-based SSE stream.
 *
 * Responsibilities:
 * - Runs the generator returned by `startFn` with an AbortSignal.
 * - Calls the appropriate callbacks for each SSEEvent type.
 * - Aborts on unmount or when `cancel()` is called.
 * - No infinite reconnect.
 */
"use client";

import { useCallback, useRef, useState } from "react";
import type {
  SSEEvent,
  SSECompleteData,
  SSEMetadataData,
  SSEStartData,
  SSEToolCallArgumentsData,
  SSEToolCallStartedData,
  SSEToolExecutionFailedData,
  SSEToolExecutionStartedData,
  SSEToolExecutionSucceededData,
} from "@/types/api";

export type StreamCallbacks = {
  onStart?: (data: SSEStartData) => void;
  onDelta: (content: string) => void;
  onCitation: (citation: SSEEvent & { event: "citation" }) => void;
  onComplete: (data: SSECompleteData) => void;
  onMetadata?: (data: SSEMetadataData) => void;
  onError: (message: string) => void;
  onToolCallStarted?: (data: SSEToolCallStartedData) => void;
  onToolCallArguments?: (data: SSEToolCallArgumentsData) => void;
  onToolExecutionStarted?: (data: SSEToolExecutionStartedData) => void;
  onToolExecutionSucceeded?: (data: SSEToolExecutionSucceededData) => void;
  onToolExecutionFailed?: (data: SSEToolExecutionFailedData) => void;
};

type StreamState = "idle" | "streaming" | "done" | "error";

export function useStream() {
  const abortRef = useRef<AbortController | null>(null);
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
      setState("streaming");

      try {
        for await (const event of generatorFn(controller.signal)) {
          if (controller.signal.aborted) break;

          switch (event.event) {
            case "start":
              callbacks.onStart?.(event.data);
              break;
            case "delta":
            case "assistant_token":
              callbacks.onDelta(event.data.content);
              break;
            case "citation":
              callbacks.onCitation(event as SSEEvent & { event: "citation" });
              break;
            case "metadata":
              callbacks.onMetadata?.(event.data);
              break;
            case "complete":
              callbacks.onComplete(event.data);
              setState("done");
              break;
            case "error":
            case "agent_failed":
              callbacks.onError(event.data.error.message);
              setState("error");
              break;
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
        callbacks.onError(err instanceof Error ? err.message : "Streaming failed");
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
