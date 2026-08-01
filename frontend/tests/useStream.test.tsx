/**
 * Streaming contract: canonical `delta`, ignore legacy `assistant_token`,
 * idempotent complete/error, safe error shapes.
 */
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useStream } from "@/lib/useStream";
import type { SSEEvent } from "@/types/api";

async function* fromEvents(events: SSEEvent[]): AsyncGenerator<SSEEvent> {
  for (const event of events) {
    yield event;
  }
}

describe("useStream canonical text contract", () => {
  it("appends delta once and ignores legacy assistant_token twins", async () => {
    const { result } = renderHook(() => useStream());
    let content = "";
    const onError = vi.fn();
    const onComplete = vi.fn();

    await act(async () => {
      await result.current.run(() => fromEvents([
        { event: "delta", data: { content: "Hello " } },
        { event: "assistant_token", data: { content: "Hello " } },
        { event: "delta", data: { content: "world" } },
        { event: "assistant_token", data: { content: "world" } },
        {
          event: "complete",
          data: {
            message: {
              id: "a1",
              conversation_id: "c1",
              role: "assistant",
              content: "Hello world",
              status: "complete",
              sequence_number: 2,
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
            },
          },
        },
      ]), {
        onDelta: (chunk) => {
          content += chunk;
        },
        onCitation: vi.fn(),
        onComplete,
        onError,
      });
    });

    expect(content).toBe("Hello world");
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
    expect(result.current.isStreaming).toBe(false);
  });

  it("ignores error after successful complete", async () => {
    const { result } = renderHook(() => useStream());
    const onError = vi.fn();
    const onComplete = vi.fn();

    await act(async () => {
      await result.current.run(() => fromEvents([
        { event: "delta", data: { content: "ok" } },
        {
          event: "complete",
          data: {
            message: {
              id: "a1",
              conversation_id: "c1",
              role: "assistant",
              content: "ok",
              status: "complete",
              sequence_number: 2,
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
            },
          },
        },
        {
          event: "error",
          data: { error: { code: "late", message: "should be ignored" } },
        },
      ]), {
        onDelta: vi.fn(),
        onCitation: vi.fn(),
        onComplete,
        onError,
      });
    });

    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it("accepts flat error shapes without throwing", async () => {
    const { result } = renderHook(() => useStream());
    const onError = vi.fn();

    await act(async () => {
      await result.current.run(() => fromEvents([
        {
          event: "error",
          data: { code: "llm_generation_error", message: "Ollama reported a generation error" } as never,
        },
      ]), {
        onDelta: vi.fn(),
        onCitation: vi.fn(),
        onComplete: vi.fn(),
        onError,
      });
    });

    expect(onError).toHaveBeenCalledWith("Ollama reported a generation error");
  });

  it("citation callback failure does not fail the stream", async () => {
    const { result } = renderHook(() => useStream());
    const onError = vi.fn();
    const onComplete = vi.fn();
    let content = "";

    await act(async () => {
      await result.current.run(() => fromEvents([
        { event: "delta", data: { content: "Answer [1]" } },
        {
          event: "citation",
          data: { citation: null as never },
        },
        {
          event: "complete",
          data: {
            message: {
              id: "a1",
              conversation_id: "c1",
              role: "assistant",
              content: "Answer [1]",
              status: "complete",
              sequence_number: 2,
              is_active: true,
              grounded: true,
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
            },
          },
        },
      ]), {
        onDelta: (chunk) => {
          content += chunk;
        },
        onCitation: () => {
          throw new Error("citation parse blew up");
        },
        onComplete,
        onError,
      });
    });

    expect(content).toBe("Answer [1]");
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it("forwards progress events", async () => {
    const { result } = renderHook(() => useStream());
    const onProgress = vi.fn();

    await act(async () => {
      await result.current.run(() => fromEvents([
        {
          event: "progress",
          data: { phase: "retrieving", message: "Searching selected documents…" },
        },
        {
          event: "complete",
          data: {
            message: {
              id: "a1",
              conversation_id: "c1",
              role: "assistant",
              content: "",
              status: "complete",
              sequence_number: 2,
              is_active: true,
              grounded: false,
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
            },
          },
        },
      ]), {
        onDelta: vi.fn(),
        onCitation: vi.fn(),
        onComplete: vi.fn(),
        onError: vi.fn(),
        onProgress,
      });
    });

    expect(onProgress).toHaveBeenCalledWith({
      phase: "retrieving",
      message: "Searching selected documents…",
    });
  });
});
