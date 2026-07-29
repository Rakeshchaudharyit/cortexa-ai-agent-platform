import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";
import RegisterPage from "@/app/register/page";
import { AuthHeader } from "@/components/AuthHeader";
import { AuthProvider } from "@/components/AuthProvider";
import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth-token";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: replaceMock,
    push: vi.fn(),
  }),
  usePathname: () => "/",
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  clearAccessToken();
  replaceMock.mockReset();
});

beforeEach(() => {
  clearAccessToken();
});

function demoUser(overrides: Record<string, unknown> = {}) {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    email: "demo@example.com",
    full_name: "Demo User",
    role: "user",
    status: "active",
    is_email_verified: false,
    created_at: "2026-07-28T00:00:00Z",
    last_login_at: null,
    ...overrides,
  };
}

function authTokenResponse() {
  return {
    user: demoUser(),
    access_token: "access-token-memory-only",
    token_type: "bearer",
    expires_in: 900,
    access_token_expires_at: "2026-07-28T00:15:00Z",
  };
}

function stubAuthApi(handlers: {
  refresh?: () => Response;
  login?: () => Response;
  register?: () => Response;
  me?: () => Response;
  logout?: () => Response;
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();

      if (url.includes("/api/v1/auth/refresh") && method === "POST") {
        return (
          handlers.refresh?.() ??
          Response.json(
            {
              error: {
                code: "invalid_refresh_token",
                message: "Invalid or expired refresh token",
                details: [],
              },
              request_id: "t",
            },
            { status: 401 },
          )
        );
      }
      if (url.includes("/api/v1/auth/login") && method === "POST") {
        return handlers.login?.() ?? Response.json(authTokenResponse());
      }
      if (url.includes("/api/v1/auth/register") && method === "POST") {
        return handlers.register?.() ?? Response.json(authTokenResponse(), { status: 201 });
      }
      if (url.includes("/api/v1/auth/me") && method === "GET") {
        return handlers.me?.() ?? Response.json(demoUser());
      }
      if (url.includes("/api/v1/auth/logout") && method === "POST") {
        return handlers.logout?.() ?? Response.json({ message: "Logged out" });
      }
      return Response.json(
        {
          error: { code: "not_found", message: "Resource not found", details: [] },
          request_id: "t",
        },
        { status: 404 },
      );
    }),
  );
}

describe("authentication UI", () => {
  it("validates registration form fields", async () => {
    stubAuthApi({});
    render(
      <AuthProvider>
        <RegisterPage />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("register-form")).toBeTruthy();
    });

    fireEvent.click(screen.getByTestId("register-submit"));
    expect(screen.getByTestId("register-error")).toHaveTextContent("All fields are required");

    fireEvent.change(screen.getByTestId("register-full-name"), {
      target: { value: "Demo User" },
    });
    fireEvent.change(screen.getByTestId("register-email"), {
      target: { value: "demo@example.com" },
    });
    fireEvent.change(screen.getByTestId("register-password"), {
      target: { value: "short" },
    });
    fireEvent.click(screen.getByTestId("register-submit"));
    expect(screen.getByTestId("register-error")).toHaveTextContent(
      "Password must be at least 12 characters",
    );
  });

  it("validates login form fields", async () => {
    stubAuthApi({});
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("login-form")).toBeTruthy();
    });

    fireEvent.click(screen.getByTestId("login-submit"));
    expect(screen.getByTestId("login-error")).toHaveTextContent(
      "Email and password are required",
    );
  });

  it("registers successfully and stores access token in memory only", async () => {
    stubAuthApi({});
    render(
      <AuthProvider>
        <RegisterPage />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("register-form")).toBeTruthy());
    fireEvent.change(screen.getByTestId("register-full-name"), {
      target: { value: "Demo User" },
    });
    fireEvent.change(screen.getByTestId("register-email"), {
      target: { value: "demo@example.com" },
    });
    fireEvent.change(screen.getByTestId("register-password"), {
      target: { value: "StrongDemoPassword123!" },
    });
    fireEvent.click(screen.getByTestId("register-submit"));

    await waitFor(() => {
      expect(getAccessToken()).toBe("access-token-memory-only");
      expect(replaceMock).toHaveBeenCalledWith("/");
    });
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });

  it("logs in successfully", async () => {
    stubAuthApi({
      login: () => Response.json(authTokenResponse()),
    });
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("login-form")).toBeTruthy());
    fireEvent.change(screen.getByTestId("login-email"), {
      target: { value: "demo@example.com" },
    });
    fireEvent.change(screen.getByTestId("login-password"), {
      target: { value: "StrongDemoPassword123!" },
    });
    fireEvent.click(screen.getByTestId("login-submit"));

    await waitFor(() => {
      expect(getAccessToken()).toBe("access-token-memory-only");
      expect(replaceMock).toHaveBeenCalledWith("/");
    });
  });

  it("shows generic login failure messaging", async () => {
    stubAuthApi({
      login: () =>
        Response.json(
          {
            error: {
              code: "invalid_credentials",
              message: "Invalid email or password",
              details: [],
            },
            request_id: "t",
          },
          { status: 401 },
        ),
    });
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("login-form")).toBeTruthy());
    fireEvent.change(screen.getByTestId("login-email"), {
      target: { value: "demo@example.com" },
    });
    fireEvent.change(screen.getByTestId("login-password"), {
      target: { value: "WrongPassword!!!" },
    });
    fireEvent.click(screen.getByTestId("login-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("login-error")).toHaveTextContent("Invalid email or password");
    });
  });

  it("restores session via refresh cookie flow", async () => {
    stubAuthApi({
      refresh: () => Response.json(authTokenResponse()),
      me: () => Response.json(demoUser()),
    });

    render(
      <AuthProvider>
        <AuthHeader />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("auth-user-display")).toHaveTextContent("Demo User");
    });
    expect(getAccessToken()).toBe("access-token-memory-only");
  });

  it("logs out and clears in-memory token", async () => {
    setAccessToken("access-token-memory-only");
    stubAuthApi({
      refresh: () => Response.json(authTokenResponse()),
      me: () => Response.json(demoUser()),
      logout: () => Response.json({ message: "Logged out" }),
    });

    render(
      <AuthProvider>
        <AuthHeader />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("logout-button")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("logout-button"));
    await waitFor(() => {
      expect(screen.getByTestId("auth-anonymous")).toBeTruthy();
      expect(getAccessToken()).toBeNull();
    });
  });

  it("clears state when refresh fails during restoration", async () => {
    setAccessToken("stale-token");
    stubAuthApi({
      me: () =>
        Response.json(
          {
            error: {
              code: "invalid_access_token",
              message: "Invalid or expired access token",
              details: [],
            },
            request_id: "t",
          },
          { status: 401 },
        ),
      refresh: () =>
        Response.json(
          {
            error: {
              code: "invalid_refresh_token",
              message: "Invalid or expired refresh token",
              details: [],
            },
            request_id: "t",
          },
          { status: 401 },
        ),
    });

    render(
      <AuthProvider>
        <AuthHeader />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("auth-anonymous")).toBeTruthy();
    });
    expect(getAccessToken()).toBeNull();
  });

  it("exposes accessible labels on auth forms", async () => {
    stubAuthApi({});
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByLabelText("Email")).toBeTruthy());
    expect(screen.getByLabelText("Password")).toBeTruthy();
  });
});

describe("authenticated request refresh-after-401", () => {
  it("retries once after refresh on 401", async () => {
    let meCalls = 0;
    let refreshCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.includes("/api/v1/auth/refresh") && method === "POST") {
          refreshCalls += 1;
          return Response.json(authTokenResponse());
        }
        if (url.includes("/api/v1/auth/me") && method === "GET") {
          meCalls += 1;
          if (meCalls === 1) {
            return Response.json(
              {
                error: {
                  code: "invalid_access_token",
                  message: "Invalid or expired access token",
                  details: [],
                },
                request_id: "t",
              },
              { status: 401 },
            );
          }
          return Response.json(demoUser());
        }
        return Response.json({ message: "ok" });
      }),
    );

    setAccessToken("expired-access");
    const { authenticatedGet } = await import("@/services/auth");
    const result = await authenticatedGet<ReturnType<typeof demoUser>>("/api/v1/auth/me");
    expect(result.ok).toBe(true);
    expect(refreshCalls).toBe(1);
    expect(meCalls).toBe(2);
    expect(getAccessToken()).toBe("access-token-memory-only");
  });

  it("does not loop forever when refresh fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.includes("/api/v1/auth/refresh") && method === "POST") {
          return Response.json(
            {
              error: {
                code: "invalid_refresh_token",
                message: "Invalid or expired refresh token",
                details: [],
              },
              request_id: "t",
            },
            { status: 401 },
          );
        }
        return Response.json(
          {
            error: {
              code: "invalid_access_token",
              message: "Invalid or expired access token",
              details: [],
            },
            request_id: "t",
          },
          { status: 401 },
        );
      }),
    );

    setAccessToken("expired-access");
    const { authenticatedGet } = await import("@/services/auth");
    const result = await authenticatedGet("/api/v1/auth/me");
    expect(result.ok).toBe(false);
    expect(getAccessToken()).toBeNull();
  });
});
