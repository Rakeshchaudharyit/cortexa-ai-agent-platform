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
