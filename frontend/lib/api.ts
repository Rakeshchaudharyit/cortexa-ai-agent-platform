import { getApiBaseUrl } from "@/lib/config";
import type { ApiResult } from "@/types/api";

const DEFAULT_TIMEOUT_MS = 8000;

type HttpMethod = "GET" | "POST" | "DELETE";

type RequestOptions = {
  /** HTTP statuses that still yield a successful ApiResult. */
  acceptStatuses?: number[];
  accessToken?: string | null;
  credentials?: RequestCredentials;
  json?: unknown;
  /** Multipart body — do not set Content-Type; the browser supplies the boundary. */
  formData?: FormData;
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
  const text = await response.text();
  if (!text.trim()) {
    return null;
  }
  try {
    return JSON.parse(text) as T;
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

export async function apiDelete<T>(
  path: string,
  options: RequestOptions = {},
): Promise<ApiResult<T>> {
  return apiRequest<T>("DELETE", path, options);
}

export async function apiRequest<T>(
  method: HttpMethod,
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
  // Only set JSON Content-Type when sending JSON. Multipart FormData must omit
  // Content-Type so the browser can attach the multipart boundary.
  if (options.json !== undefined && options.formData === undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`;
  }

  let body: BodyInit | undefined;
  if (options.formData !== undefined) {
    body = options.formData;
  } else if (options.json !== undefined) {
    body = JSON.stringify(options.json);
  }

  try {
    const response = await fetch(url, {
      method,
      headers,
      body,
      signal: controller.signal,
      cache: "no-store",
      credentials: options.credentials ?? "same-origin",
    });

    const data = await parseBody<T>(response);

    if (acceptStatuses.has(response.status)) {
      // 204 No Content has an empty body; treat as success with null data.
      if (response.status === 204 || data !== null) {
        return { ok: true, data: data as T, status: response.status };
      }
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
