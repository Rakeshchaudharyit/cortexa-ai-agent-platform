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
