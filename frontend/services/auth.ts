import { apiGet, apiPost } from "@/lib/api";
import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth-token";
import type {
  AuthTokenResponse,
  LoginRequest,
  MessageResponse,
  RegisterRequest,
  UserPublic,
} from "@/types/api";

export async function registerUser(
  body: RegisterRequest,
): Promise<{ ok: true; data: AuthTokenResponse } | { ok: false; error: string; status: number | null }> {
  const result = await apiPost<AuthTokenResponse>("/api/v1/auth/register", {
    json: body,
    credentials: "include",
    acceptStatuses: [201],
  });
  if (result.ok) {
    setAccessToken(result.data.access_token);
  }
  return result;
}

export async function loginUser(
  body: LoginRequest,
): Promise<{ ok: true; data: AuthTokenResponse } | { ok: false; error: string; status: number | null }> {
  const result = await apiPost<AuthTokenResponse>("/api/v1/auth/login", {
    json: body,
    credentials: "include",
  });
  if (result.ok) {
    setAccessToken(result.data.access_token);
  }
  return result;
}

export async function refreshSession(): Promise<
  { ok: true; data: AuthTokenResponse } | { ok: false; error: string; status: number | null }
> {
  const result = await apiPost<AuthTokenResponse>("/api/v1/auth/refresh", {
    credentials: "include",
  });
  if (result.ok) {
    setAccessToken(result.data.access_token);
  } else {
    clearAccessToken();
  }
  return result;
}

export async function logoutUser(): Promise<
  { ok: true; data: MessageResponse } | { ok: false; error: string; status: number | null }
> {
  const result = await apiPost<MessageResponse>("/api/v1/auth/logout", {
    credentials: "include",
  });
  clearAccessToken();
  return result;
}

export async function fetchCurrentUser(): Promise<
  { ok: true; data: UserPublic } | { ok: false; error: string; status: number | null }
> {
  const token = getAccessToken();
  if (!token) {
    return { ok: false, error: "Not authenticated", status: 401 };
  }
  return apiGet<UserPublic>("/api/v1/auth/me", {
    accessToken: token,
    credentials: "include",
  });
}

export async function authenticatedGet<T>(
  path: string,
): Promise<{ ok: true; data: T; status: number } | { ok: false; error: string; status: number | null }> {
  return authenticatedRequest<T>("GET", path);
}

export async function authenticatedPost<T>(
  path: string,
  json?: unknown,
): Promise<{ ok: true; data: T; status: number } | { ok: false; error: string; status: number | null }> {
  return authenticatedRequest<T>("POST", path, json);
}

async function authenticatedRequest<T>(
  method: "GET" | "POST",
  path: string,
  json?: unknown,
): Promise<{ ok: true; data: T; status: number } | { ok: false; error: string; status: number | null }> {
  const { apiRequest } = await import("@/lib/api");
  const first = await apiRequest<T>(method, path, {
    json,
    accessToken: getAccessToken(),
    credentials: "include",
  });
  if (first.ok || first.status !== 401) {
    return first;
  }

  const refreshed = await refreshSession();
  if (!refreshed.ok) {
    return { ok: false, error: refreshed.error, status: refreshed.status };
  }

  return apiRequest<T>(method, path, {
    json,
    accessToken: getAccessToken(),
    credentials: "include",
  });
}
