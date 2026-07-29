"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  fetchCurrentUser,
  loginUser,
  logoutUser,
  refreshSession,
  registerUser,
} from "@/services/auth";
import { clearAccessToken, getAccessToken } from "@/lib/auth-token";
import type { LoginRequest, RegisterRequest, UserPublic } from "@/types/api";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type AuthContextValue = {
  status: AuthStatus;
  user: UserPublic | null;
  error: string | null;
  login: (body: LoginRequest) => Promise<{ ok: true } | { ok: false; error: string }>;
  register: (body: RegisterRequest) => Promise<{ ok: true } | { ok: false; error: string }>;
  logout: () => Promise<void>;
  clearError: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<UserPublic | null>(null);
  const [error, setError] = useState<string | null>(null);

  const restore = useCallback(async () => {
    setStatus("loading");
    const existing = getAccessToken();
    if (existing) {
      const me = await fetchCurrentUser();
      if (me.ok) {
        setUser(me.data);
        setStatus("authenticated");
        return;
      }
    }

    const refreshed = await refreshSession();
    if (!refreshed.ok) {
      clearAccessToken();
      setUser(null);
      setStatus("unauthenticated");
      return;
    }

    const me = await fetchCurrentUser();
    if (me.ok) {
      setUser(me.data);
      setStatus("authenticated");
      return;
    }

    clearAccessToken();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  useEffect(() => {
    void restore();
  }, [restore]);

  const login = useCallback(async (body: LoginRequest) => {
    setError(null);
    const result = await loginUser(body);
    if (!result.ok) {
      let message = result.error || "Login failed";
      if (result.status === null) {
        message = "Unable to connect to the server";
      } else if (result.status === 401) {
        message = "Invalid email or password";
      } else if (result.status === 403) {
        message = result.error || "This account has been disabled";
      } else if (result.status >= 500) {
        message = "Something went wrong on the server. Please try again.";
      }
      setError(message);
      setStatus("unauthenticated");
      setUser(null);
      return { ok: false as const, error: message };
    }
    // Successful password login must not be overwritten by a later refresh failure.
    setUser(result.data.user);
    setStatus("authenticated");
    setError(null);
    return { ok: true as const };
  }, []);

  const register = useCallback(async (body: RegisterRequest) => {
    setError(null);
    const result = await registerUser(body);
    if (!result.ok) {
      const message = result.error || "Registration failed";
      setError(message);
      setStatus("unauthenticated");
      setUser(null);
      return { ok: false as const, error: message };
    }
    setUser(result.data.user);
    setStatus("authenticated");
    return { ok: true as const };
  }, []);

  const logout = useCallback(async () => {
    await logoutUser();
    setUser(null);
    setStatus("unauthenticated");
    setError(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      error,
      login,
      register,
      logout,
      clearError: () => setError(null),
    }),
    [status, user, error, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
