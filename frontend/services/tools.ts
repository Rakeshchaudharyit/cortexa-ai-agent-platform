import { authenticatedGet } from "@/services/auth";
import type {
  ToolExecutionDetail,
  ToolExecutionListResponse,
  ToolListResponse,
} from "@/types/api";

type ToolsResult<T> =
  | { ok: true; data: T; status: number }
  | { ok: false; error: string; status: number | null };

export async function listTools(): Promise<ToolsResult<ToolListResponse>> {
  return authenticatedGet<ToolListResponse>("/api/v1/tools");
}

export async function listToolExecutions(params?: {
  limit?: number;
  offset?: number;
  conversation_id?: string;
}): Promise<ToolsResult<ToolExecutionListResponse>> {
  const search = new URLSearchParams();
  if (params?.limit != null) search.set("limit", String(params.limit));
  if (params?.offset != null) search.set("offset", String(params.offset));
  if (params?.conversation_id) search.set("conversation_id", params.conversation_id);
  const qs = search.toString();
  return authenticatedGet<ToolExecutionListResponse>(
    `/api/v1/tool-executions${qs ? `?${qs}` : ""}`,
  );
}

export async function getToolExecution(
  executionId: string,
): Promise<ToolsResult<ToolExecutionDetail>> {
  return authenticatedGet<ToolExecutionDetail>(`/api/v1/tool-executions/${executionId}`);
}
