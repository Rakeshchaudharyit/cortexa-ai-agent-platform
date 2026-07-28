import { getApiBaseUrl } from "@/lib/config";
import type { ApiResult } from "@/types/api";

const DEFAULT_TIMEOUT_MS = 8000;

type GetOptions = {
  /** HTTP statuses that still yield a successful ApiResult with a parsed body. */
  acceptStatuses?: number[];
};

export async function apiGet<T>(
  path: string,
  options: GetOptions = {},
): Promise<ApiResult<T>> {
  const acceptStatuses = new Set(options.acceptStatuses ?? [200]);
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
      cache: "no-store",
    });

    let data: T | null = null;
    try {
      data = (await response.json()) as T;
    } catch {
      data = null;
    }

    if (acceptStatuses.has(response.status) && data !== null) {
      return { ok: true, data, status: response.status };
    }

    return {
      ok: false,
      status: response.status,
      error: `Request failed with status ${response.status}`,
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
