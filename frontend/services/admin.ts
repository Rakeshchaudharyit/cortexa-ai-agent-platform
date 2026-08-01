import { apiGet, apiPatch, apiPost, apiRequest } from "@/lib/api";
import { getAccessToken } from "@/lib/auth-token";
import type {
  AdminConversationSummary,
  AdminDashboardResponse,
  AdminDocumentSummary,
  AdminMemorySummary,
  AdminPaginated,
  AdminUserDetail,
  AdminUserSummary,
} from "@/types/admin";

function auth() {
  return { accessToken: getAccessToken() };
}

export async function fetchAdminDashboard() {
  return apiGet<AdminDashboardResponse>("/api/v1/admin/dashboard", auth());
}

export async function fetchAdminUsers(params: Record<string, string | number | undefined> = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  });
  const q = qs.toString();
  return apiGet<AdminPaginated<AdminUserSummary>>(
    `/api/v1/admin/users${q ? `?${q}` : ""}`,
    auth(),
  );
}

export async function fetchAdminUser(userId: string) {
  return apiGet<AdminUserDetail>(`/api/v1/admin/users/${userId}`, auth());
}

export async function patchAdminUser(
  userId: string,
  body: { role?: string; status?: string },
) {
  return apiPatch<{ user: AdminUserDetail; sessions_revoked: number }>(
    `/api/v1/admin/users/${userId}`,
    { ...auth(), json: body },
  );
}

export async function revokeAdminUserSessions(userId: string) {
  return apiPost<{ user_id: string; sessions_revoked: number }>(
    `/api/v1/admin/users/${userId}/revoke-sessions`,
    { ...auth(), json: {} },
  );
}

export async function fetchAdminDocuments(params: Record<string, string | number | undefined> = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  });
  const q = qs.toString();
  return apiGet<AdminPaginated<AdminDocumentSummary>>(
    `/api/v1/admin/documents${q ? `?${q}` : ""}`,
    auth(),
  );
}

export async function fetchAdminConversations(params: Record<string, string | number | undefined> = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  });
  const q = qs.toString();
  return apiGet<AdminPaginated<AdminConversationSummary>>(
    `/api/v1/admin/conversations${q ? `?${q}` : ""}`,
    auth(),
  );
}

export async function fetchAdminMemories(params: Record<string, string | number | undefined> = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  });
  const q = qs.toString();
  return apiGet<AdminPaginated<AdminMemorySummary>>(
    `/api/v1/admin/memories${q ? `?${q}` : ""}`,
    auth(),
  );
}

export async function deleteAdminDocument(documentId: string) {
  return apiRequest<null>("DELETE", `/api/v1/admin/documents/${documentId}`, {
    ...auth(),
    acceptStatuses: [204],
  });
}

export async function reprocessAdminDocument(documentId: string) {
  return apiPost(`/api/v1/admin/documents/${documentId}/reprocess`, { ...auth(), json: {} });
}
