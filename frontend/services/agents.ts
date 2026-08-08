import { apiGet, apiPatch } from "@/lib/api";
import { getAccessToken } from "@/lib/auth-token";
import { authenticatedGet, authenticatedPost } from "@/services/auth";
import type {
  AdminAgentRunDetail,
  AdminAgentRunSummary,
  AdminAgentUpdate,
  AgentApproval,
  AgentDefinition,
  AgentDefinitionList,
  AgentRunDetail,
  AgentRunFilters,
  AgentRunSummary,
  PaginatedAgentApprovals,
  PaginatedAgentEvents,
  PaginatedAgentRuns,
  PaginatedAgentTasks,
} from "@/types/agents";

function auth() {
  return { accessToken: getAccessToken() };
}

function query(filters: AgentRunFilters): string {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  if (filters.offset != null) params.set("offset", String(filters.offset));
  const value = params.toString();
  return value ? `?${value}` : "";
}

export const listAgents = () => apiGet<AgentDefinitionList>("/api/v1/agents", auth());
export const listAgentRuns = (filters: AgentRunFilters = {}) =>
  authenticatedGet<PaginatedAgentRuns<AgentRunSummary>>(`/api/v1/agent-runs${query(filters)}`);
export const getAgentRun = (runId: string) =>
  authenticatedGet<AgentRunDetail>(`/api/v1/agent-runs/${runId}`);
export const getAgentRunTasks = (runId: string) =>
  authenticatedGet<PaginatedAgentTasks>(`/api/v1/agent-runs/${runId}/tasks`);
export const getAgentRunEvents = (runId: string) =>
  authenticatedGet<PaginatedAgentEvents>(`/api/v1/agent-runs/${runId}/events`);
export const cancelAgentRun = (runId: string) =>
  authenticatedPost<AgentRunDetail>(`/api/v1/agent-runs/${runId}/cancel`, {});
export const listAgentApprovals = (status?: string) =>
  authenticatedGet<PaginatedAgentApprovals>(
    `/api/v1/agent-approvals${status ? `?status=${encodeURIComponent(status)}` : ""}`,
  );
export const getAgentApproval = (approvalId: string) =>
  authenticatedGet<AgentApproval>(`/api/v1/agent-approvals/${approvalId}`);
export const approveAgentApproval = (approvalId: string) =>
  authenticatedPost<AgentApproval>(`/api/v1/agent-approvals/${approvalId}/approve`, {
    resolution_note: null,
  });
export const rejectAgentApproval = (approvalId: string) =>
  authenticatedPost<AgentApproval>(`/api/v1/agent-approvals/${approvalId}/reject`, {
    resolution_note: null,
  });

export const listAdminAgents = () =>
  apiGet<AgentDefinitionList>("/api/v1/admin/agents", auth());
export const getAdminAgent = (agentKey: string) =>
  apiGet<AgentDefinition>(`/api/v1/admin/agents/${encodeURIComponent(agentKey)}`, auth());
export const updateAdminAgent = (agentKey: string, body: AdminAgentUpdate) =>
  apiPatch<AgentDefinition>(`/api/v1/admin/agents/${encodeURIComponent(agentKey)}`, {
    ...auth(), json: body,
  });
export const listAdminAgentRuns = (filters: AgentRunFilters = {}) =>
  apiGet<PaginatedAgentRuns<AdminAgentRunSummary>>(
    `/api/v1/admin/agent-runs${query(filters)}`,
    auth(),
  );
export const getAdminAgentRun = (runId: string) =>
  apiGet<AdminAgentRunDetail>(`/api/v1/admin/agent-runs/${runId}`, auth());
