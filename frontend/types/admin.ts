export type AdminMetricCard = {
  key: string;
  label: string;
  value: number | null;
  unit?: string | null;
  unavailable?: boolean;
  hint?: string | null;
};

export type AdminTrendPoint = {
  date: string;
  conversations: number;
  messages: number;
  tool_executions: number;
};

export type AdminStatusCount = { status: string; count: number };

export type AdminToolUsageStat = {
  tool_name: string;
  executions: number;
  succeeded: number;
  failed: number;
  success_rate: number | null;
};

export type AdminRecentActivityItem = {
  kind: string;
  summary: string;
  created_at: string;
  actor_email?: string | null;
  target_type?: string | null;
};

export type AdminSystemStatusSummary = {
  backend: string;
  postgres: string;
  redis: string;
  ollama: string;
  embedding_model: string;
  migrations: string;
  storage: string;
  database_identity?: string | null;
  app_version?: string | null;
  environment?: string | null;
};

export type AdminDashboardResponse = {
  metrics: AdminMetricCard[];
  usage_trend: AdminTrendPoint[];
  ai_activity: {
    provider: string;
    model: string;
    average_latency_ms?: number | null;
    successful_requests?: number | null;
    failed_requests?: number | null;
    available?: boolean | null;
    note?: string | null;
  };
  document_pipeline: AdminStatusCount[];
  tool_usage: AdminToolUsageStat[];
  recent_activity: AdminRecentActivityItem[];
  system_status: AdminSystemStatusSummary;
  generated_at: string;
};

export type AdminUserSummary = {
  id: string;
  email: string;
  full_name: string;
  role: "user" | "admin";
  status: "active" | "disabled";
  is_email_verified: boolean;
  created_at: string;
  last_login_at: string | null;
  conversations_count: number;
  documents_count: number;
  memories_count: number;
};

export type AdminUserDetail = AdminUserSummary & {
  active_sessions_count: number;
  tool_executions_count: number;
  tool_success_count: number;
  tool_failure_count: number;
};

export type AdminPaginated<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type AdminDocumentSummary = {
  id: string;
  filename: string;
  owner_id: string;
  owner_email?: string | null;
  owner_name?: string | null;
  media_type?: string | null;
  status: string;
  size_bytes?: number | null;
  chunk_count: number;
  created_at: string;
  processed_at?: string | null;
  processing_duration_ms?: number | null;
  error_code?: string | null;
};

export type AdminConversationSummary = {
  id: string;
  title: string;
  owner_id: string;
  owner_email?: string | null;
  owner_name?: string | null;
  status: string;
  message_count: number;
  last_activity_at?: string | null;
  grounded_mode?: boolean | null;
  memory_enabled?: boolean | null;
  tool_execution_count: number;
  created_at: string;
};

export type AdminMemorySummary = {
  id: string;
  title: string;
  owner_id: string;
  owner_email?: string | null;
  owner_name?: string | null;
  category: string;
  status: string;
  source: string;
  created_at: string;
  last_used_at?: string | null;
  use_count: number;
};

export type AdminToolSummary = {
  name: string;
  category: string;
  version: string;
  description: string;
  enabled: boolean;
  registry_enabled: boolean;
  required_roles: string[];
  timeout_seconds: number;
  confirmation_required: boolean;
  execution_count: number;
  success_rate: number | null;
  average_duration_ms: number | null;
  has_configuration: boolean;
};

export type AdminToolExecutionSummary = {
  id: string;
  tool_name: string;
  user_id: string | null;
  user_email?: string | null;
  conversation_id?: string | null;
  status: string;
  started_at: string;
  duration_ms?: number | null;
  error_code?: string | null;
  created_at: string;
};

export type AdminAnalyticsResponse = {
  range_days: 7 | 30 | 90;
  points: Array<{
    date: string;
    daily_active_users: number;
    new_users: number;
    conversations: number;
    messages: number;
    document_uploads: number;
    rag_queries: number;
    successful_responses: number;
    failed_responses: number;
    no_answer_responses: number;
    citation_count: number;
    total_tokens: number;
    memory_actions: number;
    tool_executions: number;
    tool_succeeded: number;
    tool_failed: number;
    ai_latency_ms: number | null;
    retrieval_latency_ms: number | null;
    generation_latency_ms: number | null;
    first_token_latency_ms: number | null;
  }>;
  totals: Record<string, number | null>;
  quality: {
    score: number | null;
    evaluation_score: number | null;
    feedback_score: number | null;
    success_score: number | null;
    citation_coverage_score: number | null;
    label: string;
  };
  knowledge_health: {
    total_documents: number;
    ready_documents: number;
    pending_documents: number;
    processing_documents: number;
    failed_documents: number;
    zero_chunk_documents: number;
    stale_documents: number;
    duplicate_content_groups: number;
    health_score: number | null;
  };
  feedback: {
    total: number;
    helpful: number;
    not_helpful: number;
    open_reviews: number;
    helpful_rate: number | null;
  };
  top_documents: Array<{ label: string; value: number; secondary: string | null }>;
  top_models: Array<{ label: string; value: number; secondary: string | null }>;
  evaluation_trend: Array<{ date: string; average_score: number; pass_rate: number; total_cases: number }>;
  unavailable: string[];
  generated_at: string;
};

export type AdminAuditEventSummary = {
  id: string;
  actor_user_id?: string | null;
  actor_email?: string | null;
  action: string;
  target_type: string;
  target_id?: string | null;
  safe_summary: string;
  created_at: string;
};

export type AdminSystemHealthResponse = {
  overall: "ok" | "degraded" | "unavailable";
  components: Array<{
    name: string;
    status: "ok" | "degraded" | "unavailable" | "unknown";
    message?: string | null;
    detail?: string | null;
  }>;
  ai_configuration: Record<string, unknown>;
  application: Record<string, unknown>;
  refreshed_at: string;
  guidance: string[];
};

export type AdminSettingItem = {
  key: string;
  value: unknown;
  source: "default" | "override" | "runtime";
  editable: boolean;
  description?: string | null;
};

export type AdminSettingsResponse = {
  settings: AdminSettingItem[];
  runtime: Record<string, unknown>;
  unsafe_keys_blocked: string[];
};

export type AdminUserDeletionImpact = {
  user_id: string;
  documents: number;
  document_chunks: number;
  conversations: number;
  messages: number;
  memories: number;
  refresh_sessions: number;
  tool_executions: number;
  can_delete: boolean;
  blocking_reason: string | null;
};

export type AdminUserDeleteResponse = {
  user_id: string;
  email_fingerprint: string;
  documents_deleted: number;
  document_chunks_deleted: number;
  conversations_deleted: number;
  messages_deleted: number;
  memories_deleted: number;
  refresh_sessions_revoked: number;
  tool_executions_anonymized: number;
  storage_cleanup_failures: number;
};

export type AdminDocumentDeletionImpact = {
  document_id: string;
  filename: string;
  owner_id: string;
  owner_email?: string | null;
  chunk_count: number;
  has_stored_file: boolean;
  can_delete: boolean;
  blocking_reason: string | null;
};

export type AdminConversationDeletionImpact = {
  conversation_id: string;
  title: string;
  owner_id: string;
  owner_email?: string | null;
  messages: number;
  citations: number;
  tool_executions: number;
  linked_memories: number;
  can_delete: boolean;
  blocking_reason: string | null;
};

export type AdminMemoryDeletionImpact = {
  memory_id: string;
  title: string;
  owner_id: string;
  owner_email?: string | null;
  status: string;
  has_embedding: boolean;
  can_delete: boolean;
  blocking_reason: string | null;
};

export type RagEvaluationCase = {
  id: string;
  owner_user_id: string;
  name: string;
  question: string;
  expected_answer: string | null;
  expected_keywords: string[];
  expected_document_ids: string[];
  should_answer: boolean;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type RagEvaluationRun = {
  id: string;
  status: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  average_score: number;
  provider: string | null;
  model: string | null;
  duration_ms: number | null;
  error_summary: string | null;
  created_at: string;
  completed_at: string | null;
  background_job_id: string | null;
};

export type RagEvaluationResult = {
  id: string;
  run_id: string;
  case_id: string | null;
  case_name: string;
  status: string;
  score: number;
  passed: boolean;
  groundedness_score: number;
  keyword_recall_score: number;
  citation_match_score: number;
  answerability_score: number;
  retrieval_count: number;
  citation_count: number;
  latency_ms: number | null;
  provider: string | null;
  model: string | null;
  answer_excerpt: string | null;
  error_code: string | null;
  created_at: string;
};

export type RagEvaluationRunDetail = RagEvaluationRun & { results: RagEvaluationResult[] };

export type AdminFeedbackItem = {
  id: string;
  message_id: string;
  conversation_id: string;
  user_id: string;
  user_email: string;
  sentiment: "helpful" | "not_helpful";
  reason: "incorrect" | "missing_source" | "not_relevant" | "incomplete" | "unclear" | "other" | null;
  comment: string | null;
  status: "open" | "reviewed" | "resolved";
  model: string | null;
  provider: string | null;
  grounded: boolean | null;
  citation_count: number;
  answer_excerpt: string;
  admin_note: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminFeedbackList = {
  items: AdminFeedbackItem[];
  total: number;
  open_count: number;
  helpful_count: number;
  not_helpful_count: number;
};

export type AdminBackgroundJob = {
  id: string;
  owner_user_id: string | null;
  job_type: string;
  status: "queued" | "running" | "retrying" | "succeeded" | "failed" | "dead_lettered" | "cancelled";
  progress_percent: number;
  status_message: string | null;
  result: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
  attempt_count: number;
  max_attempts: number;
  cancellation_requested: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
  resource_type?: string | null;
  resource_id?: string | null;
};

export type AdminJobList = {
  items: AdminBackgroundJob[];
  total: number;
  worker_healthy: boolean;
  worker_last_seen_at: string | null;
  queue_metrics: {
    ready_depth: number;
    delayed_depth: number;
    dead_letter_count: number;
    stale_running_count: number;
    oldest_queued_age_seconds: number | null;
  };
};
