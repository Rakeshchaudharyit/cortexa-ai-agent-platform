import { apiGet, apiPatch, apiPost, apiRequest } from "@/lib/api";
import { getAccessToken } from "@/lib/auth-token";
import type {
  AdminAnalyticsResponse,
  AdminAuditEventSummary,
  AdminConversationSummary,
  AdminDashboardResponse,
  AdminDocumentSummary,
  AdminMemorySummary,
  AdminPaginated,
  AdminSettingsResponse,
  AdminSystemHealthResponse,
  AdminToolExecutionSummary,
  AdminToolSummary,
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

export async function fetchAdminTools() {
  return apiGet<{ tools: AdminToolSummary[]; total: number }>("/api/v1/admin/tools", auth());
}

export async function patchAdminTool(
  toolName: string,
  body: { enabled?: boolean; timeout_override?: number | null },
) {
  return apiPatch<{ tool: AdminToolSummary }>(`/api/v1/admin/tools/${toolName}`, {
    ...auth(),
    json: body,
  });
}

export async function fetchAdminToolExecutions(params: Record<string, string | number | undefined> = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  });
  const q = qs.toString();
  return apiGet<AdminPaginated<AdminToolExecutionSummary>>(
    `/api/v1/admin/tool-executions${q ? `?${q}` : ""}`,
    auth(),
  );
}

export async function fetchAdminAnalytics(days: 7 | 30 | 90 = 30) {
  return apiGet<AdminAnalyticsResponse>(`/api/v1/admin/analytics?days=${days}`, auth());
}

export async function fetchAdminAudit(params: Record<string, string | number | undefined> = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  });
  const q = qs.toString();
  return apiGet<AdminPaginated<AdminAuditEventSummary>>(
    `/api/v1/admin/audit${q ? `?${q}` : ""}`,
    auth(),
  );
}

export async function fetchAdminSystem() {
  return apiGet<AdminSystemHealthResponse>("/api/v1/admin/system", auth());
}

export async function fetchAdminSettings() {
  return apiGet<AdminSettingsResponse>("/api/v1/admin/settings", auth());
}

export async function patchAdminSettings(updates: Record<string, unknown>) {
  return apiPatch<{ settings: AdminSettingsResponse["settings"]; updated_keys: string[] }>(
    "/api/v1/admin/settings",
    { ...auth(), json: { updates } },
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
