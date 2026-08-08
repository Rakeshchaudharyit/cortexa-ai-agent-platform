export type AgentRunStatus =
  | "pending"
  | "planning"
  | "running"
  | "awaiting_approval"
  | "completed"
  | "failed"
  | "cancelled"
  | "timed_out";

export type AgentTaskStatus =
  | "pending"
  | "ready"
  | "running"
  | "awaiting_approval"
  | "succeeded"
  | "skipped"
  | "failed"
  | "cancelled"
  | "timed_out";

export type AgentApprovalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "expired"
  | "cancelled";

export type AgentDefinition = {
  key: string;
  display_name: string;
  description: string;
  version: string;
  enabled: boolean;
  system_managed: boolean;
  capabilities: string[];
  allowed_tools: string[];
  maximum_steps: number;
  timeout_seconds: number;
  required_for_multi_agent: boolean;
};

export type AgentDefinitionList = { items: AgentDefinition[]; total: number };

export type AgentRunSummary = {
  id: string;
  status: AgentRunStatus;
  execution_mode: "single_agent" | "multi_agent";
  original_request_summary: string;
  safe_plan_summary: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  steps_used: number;
  llm_calls_used: number;
  tool_calls_used: number;
  task_count: number;
  correlation_id: string;
  error_code: string | null;
  safe_error_message: string | null;
  created_at: string;
};

export type AgentTask = {
  id: string;
  assigned_agent_key: string;
  task_type: string;
  objective: string;
  status: AgentTaskStatus;
  sequence: number;
  depth: number;
  requires_approval: boolean;
  result_summary: string | null;
  error_code: string | null;
  safe_error_message: string | null;
  retry_count: number;
  duration_ms: number | null;
};

export type AgentApproval = {
  id: string;
  agent_run_id: string;
  task_id: string;
  action_type: string;
  status: AgentApprovalStatus;
  safe_action_summary: string;
  requested_at: string;
  expires_at: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
};

export type SafeAgentMetadataValue = string | number | boolean | null | SafeAgentMetadataValue[];
export type SafeAgentMetadata = Record<string, SafeAgentMetadataValue>;

export type AgentRunEvent = {
  id: string;
  event_type: string;
  agent_key: string | null;
  task_id: string | null;
  safe_metadata: SafeAgentMetadata | null;
  created_at: string;
};

export type AgentRunDetail = AgentRunSummary & {
  conversation_id: string | null;
  tasks: AgentTask[];
  approvals: AgentApproval[];
  events: AgentRunEvent[];
};

export type PaginatedAgentRuns<T = AgentRunSummary> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type PaginatedAgentTasks = { items: AgentTask[]; total: number; limit: number; offset: number };
export type PaginatedAgentEvents = { items: AgentRunEvent[]; total: number; limit: number; offset: number };
export type PaginatedAgentApprovals = { items: AgentApproval[]; total: number; limit: number; offset: number };

export type AdminAgentRunSummary = AgentRunSummary & {
  user_id: string;
  conversation_id: string | null;
};

export type AdminAgentRunDetail = AdminAgentRunSummary & {
  tasks: AgentTask[];
  approvals: AgentApproval[];
  events: AgentRunEvent[];
};

export type AgentRunFilters = { status?: AgentRunStatus; limit?: number; offset?: number };

export type AdminAgentUpdate = {
  enabled?: boolean;
  timeout_seconds?: number;
  maximum_steps?: number;
  allowed_tools?: string[];
};

export type AgentLifecycleEventData = {
  event_id?: string;
  agent_run_id?: string;
  run_id?: string;
  task_id?: string;
  approval_id?: string;
  agent_key?: string;
  assigned_agent_key?: string;
  from?: string;
  to?: string;
  status?: string;
  sequence?: number;
  task_count?: number;
  duration_ms?: number;
  error_code?: string;
  message?: string;
  safe_summary?: string;
  safe_action_summary?: string;
  action_type?: string;
  requested_at?: string;
  expires_at?: string;
  reason_codes?: string[];
};

export type AgentLifecycleEventName =
  | "run_started"
  | "complexity_classified"
  | "planning_started"
  | "plan_created"
  | "safety_checked"
  | "task_ready"
  | "task_started"
  | "task_completed"
  | "task_failed"
  | "task_skipped"
  | "handoff"
  | "approval_required"
  | "approval_resolved"
  | "run_cancelled"
  | "run_completed"
  | "run_failed"
  | "run_timed_out";
