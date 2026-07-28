import { apiGet } from "@/lib/api";
import type {
  ApiResult,
  HealthResponse,
  LLMStatusResponse,
  ReadinessResponse,
  SystemInfoResponse,
} from "@/types/api";

/**
 * Typed system API helpers.
 * Fetching is client-side — see frontend/README.md.
 */
export function fetchHealth(): Promise<ApiResult<HealthResponse>> {
  return apiGet<HealthResponse>("/health");
}

export function fetchReadiness(): Promise<ApiResult<ReadinessResponse>> {
  return apiGet<ReadinessResponse>("/ready", { acceptStatuses: [200, 503] });
}

export function fetchSystemInfo(): Promise<ApiResult<SystemInfoResponse>> {
  return apiGet<SystemInfoResponse>("/api/v1/system/info");
}

export function fetchLLMStatus(): Promise<ApiResult<LLMStatusResponse>> {
  return apiGet<LLMStatusResponse>("/api/v1/llm/status");
}
