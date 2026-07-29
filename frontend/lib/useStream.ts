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
import type { SSEEvent, SSECompleteData, SSEMetadataData } from "@/types/api";

export type StreamCallbacks = {
  onDelta: (content: string) => void;
  onCitation: (citation: SSEEvent & { event: "citation" }) => void;
  onComplete: (data: SSECompleteData) => void;
  onMetadata?: (data: SSEMetadataData) => void;
  onError: (message: string) => void;
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
            case "delta":
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
              callbacks.onError(event.data.error.message);
              setState("error");
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
