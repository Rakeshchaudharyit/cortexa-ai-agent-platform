/**
 * Phase 5 — Conversation API client.
 *
 * All requests are authenticated via the in-memory access token (never
 * localStorage/sessionStorage).  Streaming uses fetch + ReadableStream so we
 * can send an Authorization header, which EventSource cannot do.
 */
import { getApiBaseUrl } from "@/lib/config";
import { getAccessToken, setAccessToken } from "@/lib/auth-token";
import { apiPost } from "@/lib/api";
import {
  authenticatedGet,
  authenticatedPost,
  authenticatedDelete,
} from "@/services/auth";
import type {
  ApiResult,
  ConversationDetail,
  ConversationListResponse,
  ConversationMessage,
  ConversationSummary,
  CreateMessageResponse,
  SSEEvent,
  UsageSummaryResponse,
} from "@/types/api";

// ─── CRUD ─────────────────────────────────────────────────────────────────────

export async function createConversation(opts?: {
  title?: string;
  document_ids?: string[] | null;
  initial_message?: string;
}): Promise<ApiResult<ConversationSummary>> {
  return authenticatedPost<ConversationSummary>("/api/v1/conversations", opts ?? {}, [200, 201]);
}

export type ListConversationsParams = {
  q?: string;
  include_archived?: boolean;
  limit?: number;
  offset?: number;
  status?: "active" | "archived";
};

export async function listConversations(
  params: ListConversationsParams = {},
): Promise<ApiResult<ConversationListResponse>> {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.include_archived) sp.set("include_archived", "true");
  if (params.limit != null) sp.set("limit", String(params.limit));
  if (params.offset != null) sp.set("offset", String(params.offset));
  if (params.status) sp.set("status", params.status);
  const qs = sp.toString() ? `?${sp.toString()}` : "";
  return authenticatedGet<ConversationListResponse>(`/api/v1/conversations${qs}`);
}

export async function getConversation(id: string): Promise<ApiResult<ConversationDetail>> {
  return authenticatedGet<ConversationDetail>(`/api/v1/conversations/${id}`);
}

export async function renameConversation(
  id: string,
  title: string,
): Promise<ApiResult<ConversationSummary>> {
  return _authenticatedPatch<ConversationSummary>(`/api/v1/conversations/${id}`, { title });
}

export async function archiveConversation(
  id: string,
): Promise<ApiResult<ConversationSummary>> {
  return authenticatedPost<ConversationSummary>(`/api/v1/conversations/${id}/archive`);
}

export async function unarchiveConversation(
  id: string,
): Promise<ApiResult<ConversationSummary>> {
  return authenticatedPost<ConversationSummary>(`/api/v1/conversations/${id}/unarchive`);
}

export async function deleteConversation(id: string): Promise<ApiResult<null>> {
  return authenticatedDelete(`/api/v1/conversations/${id}`);
}

export async function sendMessage(
  conversationId: string,
  opts: {
    content: string;
    document_ids?: string[] | null;
    top_k?: number;
    temperature?: number;
    max_tokens?: number;
  },
): Promise<ApiResult<CreateMessageResponse>> {
  return authenticatedPost<CreateMessageResponse>(
    `/api/v1/conversations/${conversationId}/messages`,
    opts,
  );
}

export async function editMessage(
  conversationId: string,
  messageId: string,
  content: string,
): Promise<ApiResult<ConversationMessage>> {
  // Backend: PATCH /{conversation_id}/messages/{message_id}
  // authenticatedRequest only exposes GET/POST/DELETE, so use fetch directly
  // with the refresh-once pattern.
  return _authenticatedPatch<ConversationMessage>(
    `/api/v1/conversations/${conversationId}/messages/${messageId}`,
    { content },
  );
}

export async function regenerate(
  conversationId: string,
  opts?: {
    document_ids?: string[] | null;
    top_k?: number;
    temperature?: number;
    max_tokens?: number;
  },
): Promise<ApiResult<CreateMessageResponse>> {
  return authenticatedPost<CreateMessageResponse>(
    `/api/v1/conversations/${conversationId}/regenerate`,
    opts ?? {},
  );
}

export async function getUsageSummary(): Promise<ApiResult<UsageSummaryResponse>> {
  return authenticatedGet<UsageSummaryResponse>("/api/v1/usage/summary");
}

// ─── SSE streaming ───────────────────────────────────────────────────────────

export type StreamMessageOpts = {
  content: string;
  document_ids?: string[] | null;
  top_k?: number;
  temperature?: number;
  max_tokens?: number;
};

/**
 * Stream a chat message using fetch-based SSE.
 *
 * Yields parsed SSEEvent objects as they arrive.  The caller is responsible
 * for stopping iteration (e.g. via AbortSignal on unmount or conversation
 * switch).  Performs the same refresh-once-on-401 pattern as
 * authenticatedRequest — but only before the stream body begins.
 *
 * @param signal AbortSignal — abort to cancel streaming (no reconnect).
 */
export async function* streamMessage(
  conversationId: string,
  opts: StreamMessageOpts,
  signal: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const url = `${getApiBaseUrl()}/api/v1/conversations/${conversationId}/messages/stream`;
  const body = JSON.stringify(opts);

  const doFetch = (token: string | null) =>
    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body,
      credentials: "include",
      signal,
      cache: "no-store",
    });

  let response = await doFetch(getAccessToken());

  // Refresh-once on 401 before the stream body starts.
  if (response.status === 401) {
    const refreshed = await apiPost<{ access_token: string }>("/api/v1/auth/refresh", {
      credentials: "include",
    });
    if (refreshed.ok) {
      setAccessToken(refreshed.data.access_token);
    }
    response = await doFetch(getAccessToken());
  }

  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => "");
    let message = `Stream request failed with status ${response.status}`;
    try {
      const parsed = JSON.parse(text) as { error?: { message?: string } };
      if (parsed.error?.message) message = parsed.error.message;
    } catch {
      // ignore
    }
    throw new Error(message);
  }

  yield* _parseSSEStream(response.body, signal);
}

// ─── Internal helpers ─────────────────────────────────────────────────────────

/**
 * Parse a ReadableStream of raw SSE bytes into typed SSEEvent objects.
 */
async function* _parseSSEStream(
  body: ReadableStream<Uint8Array>,
  signal: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const decoder = new TextDecoder();
  const reader = body.getReader();

  let buf = "";
  let currentEvent = "";

  try {
    while (true) {
      if (signal.aborted) break;

      const { done, value } = await reader.read();
      if (done) break;

      buf += decoder.decode(value, { stream: true });

      // Process complete SSE message blocks (separated by \n\n)
      const blocks = buf.split("\n\n");
      buf = blocks.pop() ?? "";

      for (const block of blocks) {
        const lines = block.split("\n");
        let eventType = currentEvent;
        let dataStr = "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice("event: ".length).trim();
          } else if (line.startsWith("data: ")) {
            dataStr += line.slice("data: ".length);
          }
        }

        if (!eventType || !dataStr) continue;

        try {
            const parsed = JSON.parse(dataStr) as Record<string, unknown>;
          yield { event: eventType, data: parsed } as SSEEvent;
        } catch {
          // malformed JSON — skip
        }

        currentEvent = "";
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * PATCH request with refresh-once on 401.  Only used for edit_message.
 */
async function _authenticatedPatch<T>(path: string, json: unknown): Promise<ApiResult<T>> {
  const base = getApiBaseUrl();
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;

  const doFetch = (token: string | null) =>
    fetch(url, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(json),
      credentials: "include",
      cache: "no-store",
    });

  let response = await doFetch(getAccessToken());

  if (response.status === 401) {
    const refreshed = await apiPost<{ access_token: string }>("/api/v1/auth/refresh", {
      credentials: "include",
    });
    if (refreshed.ok) {
      setAccessToken(refreshed.data.access_token);
    }
    response = await doFetch(getAccessToken());
  }

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    let message = `Request failed with status ${response.status}`;
    try {
      const parsed = JSON.parse(text) as { error?: { message?: string } };
      if (parsed.error?.message) message = parsed.error.message;
    } catch {
      // ignore
    }
    return { ok: false, error: message, status: response.status };
  }

  const data = (await response.json()) as T;
  return { ok: true, data, status: response.status };
}

