import {
  authenticatedDelete,
  authenticatedGet,
  authenticatedPatch,
  authenticatedPost,
} from "@/services/auth";
import type {
  MemoryAuditListResponse,
  MemoryListResponse,
  MemoryResponse,
  MemorySettingsResponse,
  MemorySettingsUpdateRequest,
  MemoryCreateRequest,
  MemoryUpdateRequest,
} from "@/types/api";

type MemoryResult<T> =
  | { ok: true; data: T; status: number }
  | { ok: false; error: string; status: number | null };

export async function listMemories(params?: {
  limit?: number;
  offset?: number;
  status?: string;
  category?: string;
  search?: string;
}): Promise<MemoryResult<MemoryListResponse>> {
  const search = new URLSearchParams();
  if (params?.limit != null) search.set("limit", String(params.limit));
  if (params?.offset != null) search.set("offset", String(params.offset));
  if (params?.status) search.set("status", params.status);
  if (params?.category) search.set("category", params.category);
  if (params?.search) search.set("search", params.search);
  const qs = search.toString();
  return authenticatedGet<MemoryListResponse>(`/api/v1/memories${qs ? `?${qs}` : ""}`);
}

export async function createMemory(
  body: MemoryCreateRequest,
): Promise<MemoryResult<MemoryResponse>> {
  return authenticatedPost<MemoryResponse>("/api/v1/memories", body);
}

export async function updateMemory(
  memoryId: string,
  body: MemoryUpdateRequest,
): Promise<MemoryResult<MemoryResponse>> {
  return authenticatedPatch<MemoryResponse>(`/api/v1/memories/${memoryId}`, body);
}

export async function deleteMemory(memoryId: string): Promise<MemoryResult<null>> {
  return authenticatedDelete(`/api/v1/memories/${memoryId}`);
}

export async function confirmMemory(memoryId: string): Promise<MemoryResult<MemoryResponse>> {
  return authenticatedPost<MemoryResponse>(`/api/v1/memories/${memoryId}/confirm`, {});
}

export async function archiveMemory(memoryId: string): Promise<MemoryResult<MemoryResponse>> {
  return authenticatedPost<MemoryResponse>(`/api/v1/memories/${memoryId}/archive`, {});
}

export async function restoreMemory(memoryId: string): Promise<MemoryResult<MemoryResponse>> {
  return authenticatedPost<MemoryResponse>(`/api/v1/memories/${memoryId}/restore`, {});
}

export async function rejectMemory(memoryId: string): Promise<MemoryResult<MemoryResponse>> {
  return authenticatedPost<MemoryResponse>(`/api/v1/memories/${memoryId}/reject`, {});
}

export async function getMemorySettings(): Promise<MemoryResult<MemorySettingsResponse>> {
  return authenticatedGet<MemorySettingsResponse>("/api/v1/memory-settings");
}

export async function updateMemorySettings(
  body: MemorySettingsUpdateRequest,
): Promise<MemoryResult<MemorySettingsResponse>> {
  return authenticatedPatch<MemorySettingsResponse>("/api/v1/memory-settings", body);
}

export async function listMemoryAudit(params?: {
  limit?: number;
  offset?: number;
}): Promise<MemoryResult<MemoryAuditListResponse>> {
  const search = new URLSearchParams();
  if (params?.limit != null) search.set("limit", String(params.limit));
  if (params?.offset != null) search.set("offset", String(params.offset));
  const qs = search.toString();
  return authenticatedGet<MemoryAuditListResponse>(
    `/api/v1/memory-audit${qs ? `?${qs}` : ""}`,
  );
}

export async function updateConversationMemory(
  conversationId: string,
  memoryEnabled: boolean,
): Promise<MemoryResult<{ memory_enabled: boolean | null }>> {
  return authenticatedPatch(`/api/v1/conversations/${conversationId}/memory`, {
    memory_enabled: memoryEnabled,
  });
}
