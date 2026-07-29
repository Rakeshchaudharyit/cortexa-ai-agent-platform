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

export type ApiResult<T> =
  | { ok: true; data: T; status: number }
  | { ok: false; error: string; status: number | null };
