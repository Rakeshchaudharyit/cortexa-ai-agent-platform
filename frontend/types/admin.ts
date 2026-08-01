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
  user_id: string;
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
    tool_executions: number;
    tool_succeeded: number;
    tool_failed: number;
  }>;
  totals: Record<string, number | null>;
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
