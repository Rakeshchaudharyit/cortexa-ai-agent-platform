export type HealthResponse = {
  status: "ok";
  service: string;
  version: string;
  environment: string;
};

export type DependencyCheck = {
  status: "ok" | "error";
  message?: string | null;
};

export type ReadinessResponse = {
  status: "ready" | "not_ready";
  checks: {
    database: DependencyCheck;
    redis: DependencyCheck;
  };
};

export type FeatureFlags = {
  ollama: boolean;
  auth: boolean;
  rag: boolean;
  memory: boolean;
  tools: boolean;
  voice: boolean;
  password_reset_dev_notice?: boolean;
};

export type SystemInfoResponse = {
  name: string;
  version: string;
  environment: string;
  api_version: string;
  features: FeatureFlags;
};

export type LLMStatus =
  | "ready"
  | "model_unavailable"
  | "provider_unavailable"
  | "misconfigured";

export type LLMStatusResponse = {
  provider: string;
  model: string;
  provider_reachable: boolean;
  model_available: boolean;
  status: LLMStatus;
  message: string;
};

export type UserRole = "user" | "admin";
export type UserStatus = "active" | "disabled";

export type UserPublic = {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  status: UserStatus;
  is_email_verified: boolean;
  created_at: string;
  last_login_at: string | null;
};

export type AuthTokenResponse = {
  user: UserPublic;
  access_token: string;
  token_type: string;
  expires_in: number;
  access_token_expires_at: string;
};

export type RegisterRequest = {
  email: string;
  password: string;
  confirm_password: string;
  full_name: string;
};

export type LoginRequest = {
  email: string;
  password: string;
};

export type ForgotPasswordRequest = {
  email: string;
};

export type ResetPasswordRequest = {
  token: string;
  new_password: string;
  confirm_password: string;
};

export type MessageResponse = {
  message: string;
};

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export type DocumentResponse = {
  id: string;
  original_filename: string;
  media_type: string;
  file_size_bytes: number;
  status: DocumentStatus;
  chunk_count: number;
  character_count: number;
  created_at: string;
  updated_at: string;
  processed_at: string | null;
  error_code: string | null;
  error_message: string | null;
  title: string | null;
  folder_id: string | null;
  folder_name: string | null;
  tags: string[];
  version_number: number;
  knowledge_document_id: string | null;
  lifecycle_state: string;
  is_active_version: boolean;
  supersedes_document_id: string | null;
  archived_at: string | null;
  is_archived: boolean;
  processing_mode: "synchronous" | "background";
  background_job_id?: string | null;
  job_status?: string | null;
  job_progress_percent?: number | null;
  job_status_message?: string | null;
};

export type DocumentVersionSummary = {
  id: string;
  version_number: number;
  title: string | null;
  original_filename: string;
  lifecycle_state: string;
  is_active_version: boolean;
  status: DocumentStatus;
  chunk_count: number;
  character_count: number;
  created_at: string;
  processed_at: string | null;
  archived_at: string | null;
};

export type DocumentVersionHistoryResponse = {
  knowledge_document_id: string;
  title: string;
  active_version_id: string | null;
  versions: DocumentVersionSummary[];
};

export type KnowledgeDocumentEventResponse = {
  id: string;
  document_id: string | null;
  event_type: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type DocumentTimelineResponse = {
  knowledge_document_id: string;
  items: KnowledgeDocumentEventResponse[];
};

export type DocumentVersionCompareResponse = {
  left: DocumentVersionSummary;
  right: DocumentVersionSummary;
  changed_fields: string[];
  chunk_count_delta: number;
  character_count_delta: number;
};

export type DocumentFolderResponse = {
  id: string;
  name: string;
  description: string | null;
  document_count: number;
  created_at: string;
  updated_at: string;
};

export type DocumentFolderListResponse = {
  items: DocumentFolderResponse[];
  total: number;
};

export type DocumentMetadataUpdate = {
  title?: string | null;
  folder_id?: string | null;
  tags?: string[];
};

export type DocumentListResponse = {
  items: DocumentResponse[];
  total: number;
  limit: number;
  offset: number;
};

export type RagCitation = {
  citation_id: string;
  document_id: string;
  filename: string;
  chunk_id: string;
  chunk_index: number;
  page_number: number | null;
  excerpt: string;
  similarity: number;
};

export type RagQueryRequest = {
  question: string;
  document_ids?: string[] | null;
  top_k?: number | null;
  temperature?: number | null;
  max_tokens?: number | null;
};

export type RagQueryResponse = {
  answer: string;
  citations: RagCitation[];
  retrieval_count: number;
  model: string;
  provider: string;
  grounded: boolean;
  latency_ms: number | null;
};

export type EmbeddingStatusResponse = {
  provider: string;
  model: string;
  provider_reachable: boolean;
  model_available: boolean;
  configured_dimension: number;
  status: string;
  message: string;
};

/**
 * Successful API results always include `status`. For HTTP 204, `data` may be
 * `null` (no JSON body). Callers that expect a body should use a non-null `T`.
 */
export type ApiResult<T> =
  | { ok: true; data: T; status: number }
  | { ok: false; error: string; status: number | null };

// ─── Phase 5: Conversations ───────────────────────────────────────────────────

export type ConversationStatus = "active" | "archived";

export type ConversationSummary = {
  id: string;
  title: string;
  status: ConversationStatus;
  message_count: number;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
  archived_at: string | null;
  title_is_auto: boolean;
  summary_preview: string | null;
};

export type MessageCitation = {
  id: string;
  citation_index: number;
  citation_id: string;
  document_id: string | null;
  chunk_id: string | null;
  filename: string;
  page_number: number | null;
  chunk_index: number;
  excerpt: string;
  similarity_score: number | null;
};


export type MessageFeedback = {
  id: string;
  sentiment: "helpful" | "not_helpful";
  reason: "incorrect" | "missing_source" | "not_relevant" | "incomplete" | "unclear" | "other" | null;
  comment: string | null;
  status: "open" | "reviewed" | "resolved";
  created_at: string;
  updated_at: string;
};

export type ConversationMessage = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  status: "pending" | "streaming" | "complete" | "failed";
  sequence_number: number;
  is_active: boolean;
  grounded: boolean | null;
  model: string | null;
  provider: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  latency_ms: number | null;
  finish_reason: string | null;
  error_code: string | null;
  regenerated_from_message_id: string | null;
  edited_from_message_id: string | null;
  created_at: string;
  updated_at: string;
  citations: MessageCitation[];
  tool_execution_ids?: string[];
  tool_executions?: ToolExecutionSummary[];
  agent_run_id?: string | null;
  feedback?: MessageFeedback | null;
};

export type ToolDefinition = {
  name: string;
  description: string;
  version: string;
  category: string;
  requires_confirmation: boolean;
  enabled: boolean;
  parameters: Record<string, unknown>;
};

export type ToolListResponse = {
  tools: ToolDefinition[];
  total: number;
};

export type ToolExecutionStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "denied"
  | "timed_out"
  | "cancelled";

export type ToolExecutionSummary = {
  id: string;
  tool_name: string;
  tool_version: string;
  status: ToolExecutionStatus | string;
  conversation_id: string | null;
  message_id: string | null;
  arguments_summary: Record<string, unknown> | null;
  result_summary: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  created_at: string;
};

export type ToolExecutionDetail = ToolExecutionSummary & {
  arguments_json: Record<string, unknown> | null;
  result_json: Record<string, unknown> | null;
  correlation_id: string | null;
};

export type ToolExecutionListResponse = {
  items: ToolExecutionSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type ToolActivityItem = {
  id: string;
  tool_name: string;
  status: "started" | "running" | "succeeded" | "failed";
  arguments?: Record<string, unknown>;
  result?: Record<string, unknown>;
  error_message?: string | null;
  execution_id?: string | null;
};

export type ConversationDetail = {
  id: string;
  title: string;
  status: ConversationStatus;
  message_count: number;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
  archived_at: string | null;
  title_is_auto: boolean;
  summary: string | null;
  default_document_scope: string[] | null;
  messages: ConversationMessage[];
  has_more_messages: boolean;
  memory_enabled?: boolean | null;
  memory_context_used?: number;
  active_agent_run_id?: string | null;
};

export type ConversationListResponse = {
  items: ConversationSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type CreateMessageResponse = {
  conversation: ConversationSummary;
  user_message: ConversationMessage;
  assistant_message: ConversationMessage;
};

export type UsageSummaryResponse = {
  conversations: number;
  active_conversations: number;
  messages: number;
  user_messages: number;
  assistant_messages: number;
  documents: number;
  known_prompt_tokens: number;
  known_completion_tokens: number;
  known_total_tokens: number;
  average_latency_ms: number | null;
};

// ─── SSE streaming event types ────────────────────────────────────────────────

export type SSEStartData = {
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
};

export type SSEDeltaData = { content: string };

export type SSECitationData = { citation: MessageCitation };

export type SSEProgressData = {
  phase: string;
  message: string;
  retrieved_chunk_count?: number;
  citation_count?: number;
  elapsed_ms?: number;
};

export type SSEMetadataData = {
  model: string | null;
  provider: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  latency_ms: number | null;
  tool_execution_ids?: string[];
  provider_streaming?: boolean | null;
  time_to_first_token_ms?: number | null;
  total_generation_ms?: number | null;
  retrieval_ms?: number | null;
  retrieved_chunk_count?: number | null;
  citation_count?: number | null;
  agent_run_id?: string;
  execution_mode?: "single_agent" | "multi_agent";
  approval_required?: boolean;
};

export type SSECompleteData = { message: ConversationMessage };

export type SSEErrorData = { error: { code: string; message: string } };

export type SSEToolCallStartedData = {
  tool_call_id: string;
  tool_name: string;
  iteration?: number;
};

export type SSEToolCallArgumentsData = {
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
};

export type SSEToolExecutionStartedData = {
  execution_id: string;
  tool_call_id?: string;
  tool_name: string;
};

export type SSEToolExecutionSucceededData = {
  execution_id: string | null;
  tool_call_id?: string;
  tool_name: string;
  result?: Record<string, unknown>;
};

export type SSEToolExecutionFailedData = {
  execution_id: string | null;
  tool_call_id?: string;
  tool_name: string;
  error_code?: string;
  error_message?: string;
};

export type SSEEvent =
  | { event: "start"; data: SSEStartData }
  | { event: "delta"; data: SSEDeltaData }
  | { event: "citation"; data: SSECitationData }
  | { event: "progress"; data: SSEProgressData }
  | { event: "metadata"; data: SSEMetadataData }
  | { event: "complete"; data: SSECompleteData }
  | { event: "error"; data: SSEErrorData }
  | { event: "agent_started"; data: Record<string, unknown> }
  | { event: "tool_call_started"; data: SSEToolCallStartedData }
  | { event: "tool_call_arguments"; data: SSEToolCallArgumentsData }
  | { event: "tool_execution_started"; data: SSEToolExecutionStartedData }
  | { event: "tool_execution_succeeded"; data: SSEToolExecutionSucceededData }
  | { event: "tool_execution_failed"; data: SSEToolExecutionFailedData }
  | { event: "assistant_token"; data: SSEDeltaData }
  | { event: "assistant_completed"; data: { content: string } }
  | { event: "agent_completed"; data: Record<string, unknown> }
  | { event: "agent_failed"; data: SSEErrorData }
  | { event: "memory_retrieval_started"; data: Record<string, unknown> }
  | {
      event: "memory_retrieval_completed";
      data: {
        count: number;
        references?: Array<{ title: string; category: string }>;
      };
    }
  | {
      event: "memory_candidate_proposed";
      data: {
        title: string;
        category: string;
        reason?: string;
        status?: string;
      };
    }
  | {
      event: "memory_saved";
      data: { title?: string; category?: string; status?: string };
    }
  | {
      event: "memory_updated";
      data: Record<string, unknown>;
    }
  | {
      event: "memory_archived";
      data: { count?: number; titles?: string[] };
    }
  | { event: "memory_deleted"; data: Record<string, unknown> }
  | {
      event: "memory_action_failed";
      data: { code?: string; message?: string };
    }
  | {
      event:
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
      data: import("@/types/agents").AgentLifecycleEventData;
    };

export type MemoryCategory =
  | "preference"
  | "personal_context"
  | "project"
  | "instruction"
  | "workflow"
  | "technical_context"
  | "decision"
  | "goal"
  | "relationship_context"
  | "other";

export type MemoryStatus = "proposed" | "active" | "archived" | "rejected" | "deleted";

export type MemorySource =
  | "explicit_user_request"
  | "assistant_suggestion"
  | "automatic_extraction"
  | "imported"
  | "system_generated";

export type MemoryResponse = {
  id: string;
  category: MemoryCategory;
  status: MemoryStatus;
  title: string;
  content: string;
  source: MemorySource;
  confidence: "high" | "medium" | "low" | null;
  importance: number;
  confirmation_required: boolean;
  confirmed_at: string | null;
  last_used_at: string | null;
  use_count: number;
  expires_at: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
  source_conversation_id: string | null;
};

export type MemoryListResponse = {
  items: MemoryResponse[];
  total: number;
  limit: number;
  offset: number;
};

export type MemorySettingsResponse = {
  memory_enabled: boolean;
  automatic_extraction_enabled: boolean;
  suggestions_enabled: boolean;
  require_confirmation: boolean;
  include_memories_in_chat: boolean;
  maximum_active_memories: number;
  default_expiration_days: number | null;
  created_at: string;
  updated_at: string;
};

export type MemorySettingsUpdateRequest = Partial<{
  memory_enabled: boolean;
  automatic_extraction_enabled: boolean;
  suggestions_enabled: boolean;
  require_confirmation: boolean;
  include_memories_in_chat: boolean;
  maximum_active_memories: number;
  default_expiration_days: number | null;
}>;

export type MemoryCreateRequest = {
  title: string;
  content: string;
  category?: MemoryCategory;
  importance?: number;
  expires_at?: string | null;
  confirmation_required?: boolean | null;
};

export type MemoryUpdateRequest = {
  title?: string;
  content?: string;
  category?: MemoryCategory;
  importance?: number;
  expires_at?: string | null;
};

export type MemoryAuditEventResponse = {
  id: string;
  memory_id: string | null;
  event_type: string;
  conversation_id: string | null;
  message_id: string | null;
  safe_metadata_json: Record<string, unknown> | null;
  created_at: string;
  correlation_id: string | null;
};

export type MemoryAuditListResponse = {
  items: MemoryAuditEventResponse[];
  total: number;
  limit: number;
  offset: number;
};
