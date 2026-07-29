import { getApiBaseUrl } from "@/lib/config";
import type { ApiResult } from "@/types/api";

const DEFAULT_TIMEOUT_MS = 8000;

type RequestOptions = {
  /** HTTP statuses that still yield a successful ApiResult with a parsed body. */
  acceptStatuses?: number[];
  accessToken?: string | null;
  credentials?: RequestCredentials;
  json?: unknown;
  timeoutMs?: number;
};

type ErrorEnvelope = {
  error?: { message?: string; code?: string };
};

function buildUrl(path: string): string {
  const baseUrl = getApiBaseUrl();
  return `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

async function parseBody<T>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

function errorMessage(data: unknown, fallback: string): string {
  const envelope = data as ErrorEnvelope | null;
  const message = envelope?.error?.message;
  if (typeof message === "string" && message.trim()) {
    return message;
  }
  return fallback;
}

export async function apiGet<T>(
  path: string,
  options: RequestOptions = {},
): Promise<ApiResult<T>> {
  return apiRequest<T>("GET", path, options);
}

export async function apiPost<T>(
  path: string,
  options: RequestOptions = {},
): Promise<ApiResult<T>> {
  return apiRequest<T>("POST", path, options);
}

export async function apiRequest<T>(
  method: "GET" | "POST",
  path: string,
  options: RequestOptions = {},
): Promise<ApiResult<T>> {
  const acceptStatuses = new Set(options.acceptStatuses ?? [200]);
  const url = buildUrl(path);
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(),
    options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  );

  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`;
  }

  try {
    const response = await fetch(url, {
      method,
      headers,
      body: options.json !== undefined ? JSON.stringify(options.json) : undefined,
      signal: controller.signal,
      cache: "no-store",
      credentials: options.credentials ?? "same-origin",
    });

    const data = await parseBody<T>(response);

    if (acceptStatuses.has(response.status) && data !== null) {
      return { ok: true, data, status: response.status };
    }

    return {
      ok: false,
      status: response.status,
      error: errorMessage(data, `Request failed with status ${response.status}`),
    };
  } catch (error) {
    const message =
      error instanceof Error && error.name === "AbortError"
        ? "Backend request timed out"
        : "Backend unavailable";
    return { ok: false, error: message, status: null };
  } finally {
    clearTimeout(timer);
  }
}
