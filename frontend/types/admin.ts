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
