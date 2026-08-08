import { apiDelete, apiGet, apiPatch, apiPost, apiRequest } from "@/lib/api";
import { getAccessToken } from "@/lib/auth-token";
import { getApiBaseUrl } from "@/lib/config";
import type {
  AdminAnalyticsResponse,
  AdminBackgroundJob,
  AdminAuditEventSummary,
  AdminConversationDeletionImpact,
  AdminConversationSummary,
  AdminDashboardResponse,
  AdminDocumentDeletionImpact,
  AdminDocumentSummary,
  AdminFeedbackItem,
  AdminFeedbackList,
  AdminJobList,
  AdminMemoryDeletionImpact,
  AdminMemorySummary,
  AdminPaginated,
  AdminSettingsResponse,
  AdminSystemHealthResponse,
  AdminToolExecutionSummary,
  AdminToolSummary,
  AdminUserDeleteResponse,
  AdminUserDeletionImpact,
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

export async function resetAdminSetting(key: string) {
  return apiDelete<{ settings: AdminSettingsResponse["settings"]; updated_keys: string[] }>(
    `/api/v1/admin/settings/${encodeURIComponent(key)}`,
    auth(),
  );
}

export async function fetchUserDeletionImpact(userId: string) {
  return apiGet<AdminUserDeletionImpact>(`/api/v1/admin/users/${userId}/deletion-impact`, auth());
}

export async function deactivateAdminUser(userId: string) {
  return apiPost<{ user: AdminUserDetail; sessions_revoked: number }>(
    `/api/v1/admin/users/${userId}/deactivate`,
    { ...auth(), json: {} },
  );
}

export async function activateAdminUser(userId: string) {
  return apiPost<{ user: AdminUserDetail; sessions_revoked: number }>(
    `/api/v1/admin/users/${userId}/activate`,
    { ...auth(), json: {} },
  );
}

export async function deleteAdminUser(userId: string, confirmationEmail: string) {
  return apiDelete<AdminUserDeleteResponse>(`/api/v1/admin/users/${userId}`, {
    ...auth(),
    json: { confirmation_email: confirmationEmail },
  });
}

export async function fetchDocumentDeletionImpact(documentId: string) {
  return apiGet<AdminDocumentDeletionImpact>(
    `/api/v1/admin/documents/${documentId}/deletion-impact`,
    auth(),
  );
}

export async function deleteAdminDocument(documentId: string, confirmationFilename: string) {
  return apiRequest<null>("DELETE", `/api/v1/admin/documents/${documentId}`, {
    ...auth(),
    json: { confirmation_filename: confirmationFilename },
    acceptStatuses: [204],
  });
}

export async function reprocessAdminDocument(documentId: string) {
  return apiPost(`/api/v1/admin/documents/${documentId}/reprocess`, { ...auth(), json: {} });
}

export async function fetchConversationDeletionImpact(conversationId: string) {
  return apiGet<AdminConversationDeletionImpact>(
    `/api/v1/admin/conversations/${conversationId}/deletion-impact`,
    auth(),
  );
}

export async function archiveAdminConversation(conversationId: string) {
  return apiPost<AdminConversationSummary>(
    `/api/v1/admin/conversations/${conversationId}/archive`,
    { ...auth(), json: {} },
  );
}

export async function deleteAdminConversation(conversationId: string) {
  return apiRequest<null>("DELETE", `/api/v1/admin/conversations/${conversationId}`, {
    ...auth(),
    json: { confirm: true },
    acceptStatuses: [204],
  });
}

export async function fetchMemoryDeletionImpact(memoryId: string) {
  return apiGet<AdminMemoryDeletionImpact>(
    `/api/v1/admin/memories/${memoryId}/deletion-impact`,
    auth(),
  );
}

export async function archiveAdminMemory(memoryId: string) {
  return apiPost(`/api/v1/admin/memories/${memoryId}/archive`, { ...auth(), json: {} });
}

export async function deleteAdminMemory(memoryId: string) {
  return apiRequest<null>("DELETE", `/api/v1/admin/memories/${memoryId}`, {
    ...auth(),
    acceptStatuses: [204],
  });
}

export async function resetAdminToolConfiguration(toolName: string) {
  return apiDelete<{ tool: AdminToolSummary }>(
    `/api/v1/admin/tools/${encodeURIComponent(toolName)}/configuration`,
    auth(),
  );
}

export async function acknowledgeAdminSession() {
  return apiRequest<null>("POST", "/api/v1/admin/session/acknowledge", {
    ...auth(),
    acceptStatuses: [204],
  });
}

export async function reportAdminLoginDenied() {
  return apiRequest<null>("POST", "/api/v1/admin/session/denied", {
    ...auth(),
    acceptStatuses: [204],
  });
}

export async function fetchEvaluationCases() {
  return apiGet<{ items: import("@/types/admin").RagEvaluationCase[]; total: number }>(
    "/api/v1/admin/evaluations/cases",
    auth(),
  );
}

export async function createEvaluationCase(body: {
  owner_user_id: string;
  name: string;
  question: string;
  expected_keywords: string[];
  should_answer: boolean;
  enabled: boolean;
}) {
  return apiPost<import("@/types/admin").RagEvaluationCase>(
    "/api/v1/admin/evaluations/cases",
    { ...auth(), json: body, acceptStatuses: [201] },
  );
}

export async function deleteEvaluationCase(caseId: string) {
  return apiDelete<null>(
    `/api/v1/admin/evaluations/cases/${encodeURIComponent(caseId)}`,
    { ...auth(), acceptStatuses: [204] },
  );
}

export async function runRagEvaluation() {
  return apiPost<import("@/types/admin").RagEvaluationRun>(
    "/api/v1/admin/evaluations/runs",
    { ...auth(), json: {}, acceptStatuses: [202] },
  );
}

export async function queueEvaluationExport(runId: string) {
  return apiPost<{ job_id: string }>(
    `/api/v1/admin/evaluations/runs/${encodeURIComponent(runId)}/export`,
    { ...auth(), json: {}, acceptStatuses: [202] },
  );
}

export async function downloadEvaluationExport(jobId: string) {
  const token = getAccessToken();
  const response = await fetch(
    `${getApiBaseUrl()}/api/v1/admin/evaluations/exports/${encodeURIComponent(jobId)}/download`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {}, credentials: "same-origin" },
  );
  if (!response.ok) return { ok: false as const, error: `Download failed with status ${response.status}` };
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] ?? `rag-evaluation-${jobId}.csv`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return { ok: true as const };
}

export async function fetchEvaluationRuns() {
  return apiGet<{ items: import("@/types/admin").RagEvaluationRun[]; total: number }>(
    "/api/v1/admin/evaluations/runs",
    auth(),
  );
}

export async function fetchEvaluationRun(runId: string) {
  return apiGet<import("@/types/admin").RagEvaluationRunDetail>(
    `/api/v1/admin/evaluations/runs/${runId}`,
    auth(),
  );
}


export async function fetchAdminFeedback(params: { status?: string; sentiment?: string } = {}) {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.sentiment) qs.set("sentiment", params.sentiment);
  const query = qs.toString();
  return apiGet<AdminFeedbackList>(`/api/v1/admin/feedback${query ? `?${query}` : ""}`, auth());
}

export async function updateAdminFeedback(
  feedbackId: string,
  body: { status: "open" | "reviewed" | "resolved"; admin_note?: string },
) {
  return apiPatch<AdminFeedbackItem>(`/api/v1/admin/feedback/${feedbackId}`, {
    ...auth(),
    json: body,
  });
}

export async function fetchAdminJobs(status?: string, jobType?: string) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (jobType) params.set("job_type", jobType);
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiGet<AdminJobList>(`/api/v1/admin/jobs${query}`, auth());
}

export async function createAdminDemoJob(idempotencyKey?: string) {
  return apiRequest<AdminBackgroundJob>(
    "POST",
    "/api/v1/admin/jobs/demo",
    {
      ...auth(),
      json: {
        job_type: "demo.validation",
        payload: { source: "admin_job_monitor" },
        idempotency_key: idempotencyKey ?? null,
        max_attempts: 3,
      },
      acceptStatuses: [201],
    },
  );
}

export async function cancelAdminJob(jobId: string) {
  return apiPost<AdminBackgroundJob>(
    `/api/v1/admin/jobs/${jobId}/cancel`,
    { ...auth(), json: {} },
  );
}

export async function requeueAdminJob(jobId: string) {
  return apiPost<AdminBackgroundJob>(
    `/api/v1/admin/jobs/${jobId}/requeue`,
    { ...auth(), json: {} },
  );
}

export async function bulkAdminJobs(jobIds: string[], action: "cancel" | "requeue") {
  return apiPost<{ action: string; requested: number; changed: number; skipped: number }>(
    "/api/v1/admin/jobs/bulk",
    { ...auth(), json: { job_ids: jobIds, action } },
  );
}
