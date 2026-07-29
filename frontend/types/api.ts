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
  full_name: string;
};

export type LoginRequest = {
  email: string;
  password: string;
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
  processing_mode: "synchronous";
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

export type SSEMetadataData = {
  model: string | null;
  provider: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  latency_ms: number | null;
};

export type SSECompleteData = { message: ConversationMessage };

export type SSEErrorData = { error: { code: string; message: string } };

export type SSEEvent =
  | { event: "start"; data: SSEStartData }
  | { event: "delta"; data: SSEDeltaData }
  | { event: "citation"; data: SSECitationData }
  | { event: "metadata"; data: SSEMetadataData }
  | { event: "complete"; data: SSECompleteData }
  | { event: "error"; data: SSEErrorData };
