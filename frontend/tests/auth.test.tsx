import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ForgotPasswordPage from "@/app/forgot-password/page";
import LoginPage from "@/app/login/page";
import RegisterPage from "@/app/register/page";
import ResetPasswordPage from "@/app/reset-password/page";
import { AuthHeader } from "@/components/AuthHeader";
import { AuthProvider } from "@/components/AuthProvider";
import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth-token";
import { resetRefreshCoordinatorForTests } from "@/lib/refresh-coordinator";
import { authenticatedGet, refreshSession } from "@/services/auth";

const replaceMock = vi.fn();
const searchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: replaceMock,
    push: vi.fn(),
  }),
  usePathname: () => "/",
  useSearchParams: () => searchParams,
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  clearAccessToken();
  resetRefreshCoordinatorForTests();
  replaceMock.mockReset();
  Array.from(searchParams.keys()).forEach((key) => searchParams.delete(key));
});

beforeEach(() => {
  clearAccessToken();
  resetRefreshCoordinatorForTests();
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
  forgot?: () => Response;
  reset?: () => Response;
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
      if (url.includes("/api/v1/auth/forgot-password") && method === "POST") {
        return (
          handlers.forgot?.() ??
          Response.json({
            message:
              "If an account exists for that email, password reset instructions have been prepared.",
          })
        );
      }
      if (url.includes("/api/v1/auth/reset-password") && method === "POST") {
        return (
          handlers.reset?.() ??
          Response.json({
            message: "Password reset successfully. You can now log in with your new password.",
          })
        );
      }
      if (url.includes("/api/v1/auth/me") && method === "GET") {
        return handlers.me?.() ?? Response.json(demoUser());
      }
      if (url.includes("/api/v1/auth/logout") && method === "POST") {
        return handlers.logout?.() ?? Response.json({ message: "Logged out" });
      }
      if (url.includes("/api/v1/system/info") && method === "GET") {
        return Response.json({
          name: "Cortexa AI Agent Platform",
          version: "0.1.0",
          environment: "development",
          api_version: "v1",
          features: {
            ollama: true,
            auth: true,
            rag: true,
            memory: true,
            tools: false,
            voice: false,
            password_reset_dev_notice: true,
          },
        });
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
    fireEvent.change(screen.getByTestId("register-confirm-password"), {
      target: { value: "short" },
    });
    fireEvent.click(screen.getByTestId("register-submit"));
    expect(screen.getByTestId("register-error")).toHaveTextContent(
      "Password must be at least 12 characters",
    );
  });

  it("rejects mismatched registration passwords", async () => {
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
    fireEvent.change(screen.getByTestId("register-confirm-password"), {
      target: { value: "DifferentPassword123!" },
    });
    fireEvent.click(screen.getByTestId("register-submit"));
    expect(screen.getByTestId("register-error")).toHaveTextContent("Passwords do not match");
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
    fireEvent.change(screen.getByTestId("register-confirm-password"), {
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

  it("shows forgot-password link on login page", async () => {
    stubAuthApi({});
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("forgot-password-link")).toBeTruthy());
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

  it("maps network errors away from invalid credentials", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
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
      expect(screen.getByTestId("login-error")).toHaveTextContent(
        "Unable to connect to the server",
      );
    });
  });

  it("maps backend 500 away from invalid credentials", async () => {
    stubAuthApi({
      login: () =>
        Response.json(
          {
            error: { code: "internal_error", message: "An unexpected error occurred", details: [] },
            request_id: "t",
          },
          { status: 500 },
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
      target: { value: "StrongDemoPassword123!" },
    });
    fireEvent.click(screen.getByTestId("login-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("login-error")).toHaveTextContent(
        "Something went wrong on the server",
      );
    });
  });

  it("toggles password visibility", async () => {
    stubAuthApi({});
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("login-password")).toBeTruthy());
    expect(screen.getByTestId("login-password")).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByTestId("login-password-toggle"));
    expect(screen.getByTestId("login-password")).toHaveAttribute("type", "text");
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

  it("hides admin-only navigation for normal users", async () => {
    stubAuthApi({
      refresh: () => Response.json(authTokenResponse()),
      me: () => Response.json(demoUser({ role: "user" })),
    });

    render(
      <AuthProvider>
        <AuthHeader />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("auth-user-display")).toHaveTextContent("Demo User");
    });
    expect(screen.queryByTestId("admin-nav-link")).toBeNull();
    expect(screen.getByTestId("auth-nav").textContent?.toLowerCase()).not.toContain("admin");
    expect(screen.getByTestId("tools-link").getAttribute("href")).toBe("/tools");
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

describe("forgot / reset password UI", () => {
  it("shows generic success for known and unknown emails", async () => {
    vi.stubEnv("NEXT_PUBLIC_PASSWORD_RESET_DEV_NOTICE", "true");
    stubAuthApi({});
    render(<ForgotPasswordPage />);
    await waitFor(() => expect(screen.getByTestId("forgot-password-form")).toBeTruthy());
    await waitFor(() =>
      expect(screen.getByTestId("forgot-password-dev-notice")).toHaveTextContent(
        "Email delivery is not configured",
      ),
    );
    fireEvent.change(screen.getByTestId("forgot-password-email"), {
      target: { value: "anyone@example.com" },
    });
    fireEvent.click(screen.getByTestId("forgot-password-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("forgot-password-success")).toHaveTextContent(
        "If an account exists for that email",
      );
    });
  });

  it("shows network error on forgot-password", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    render(<ForgotPasswordPage />);
    await waitFor(() => expect(screen.getByTestId("forgot-password-form")).toBeTruthy());
    fireEvent.change(screen.getByTestId("forgot-password-email"), {
      target: { value: "anyone@example.com" },
    });
    fireEvent.click(screen.getByTestId("forgot-password-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("forgot-password-error")).toHaveTextContent(
        "Unable to connect to the server",
      );
    });
  });

  it("resets password from token query and clears URL token", async () => {
    searchParams.set("token", "raw-reset-token-value");
    stubAuthApi({});
    render(<ResetPasswordPage />);
    await waitFor(() => expect(screen.getByTestId("reset-password-form")).toBeTruthy());
    fireEvent.change(screen.getByTestId("reset-password-new"), {
      target: { value: "BrandNewSecurePass456!" },
    });
    fireEvent.change(screen.getByTestId("reset-password-confirm"), {
      target: { value: "BrandNewSecurePass456!" },
    });
    fireEvent.click(screen.getByTestId("reset-password-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("reset-password-success")).toBeTruthy();
      expect(replaceMock).toHaveBeenCalledWith("/reset-password");
    });
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });

  it("shows mismatch and invalid token errors", async () => {
    searchParams.set("token", "raw-reset-token-value");
    stubAuthApi({});
    render(<ResetPasswordPage />);
    await waitFor(() => expect(screen.getByTestId("reset-password-form")).toBeTruthy());
    fireEvent.change(screen.getByTestId("reset-password-new"), {
      target: { value: "BrandNewSecurePass456!" },
    });
    fireEvent.change(screen.getByTestId("reset-password-confirm"), {
      target: { value: "DifferentPassword!!!" },
    });
    fireEvent.click(screen.getByTestId("reset-password-submit"));
    expect(screen.getByTestId("reset-password-error")).toHaveTextContent(
      "Passwords do not match",
    );

    cleanup();
    stubAuthApi({
      reset: () =>
        Response.json(
          {
            error: {
              code: "password_reset_token_invalid",
              message: "This password reset link is invalid or has expired.",
              details: [],
            },
            request_id: "t",
          },
          { status: 400 },
        ),
    });
    render(<ResetPasswordPage />);
    await waitFor(() => expect(screen.getByTestId("reset-password-form")).toBeTruthy());
    fireEvent.change(screen.getByTestId("reset-password-new"), {
      target: { value: "BrandNewSecurePass456!" },
    });
    fireEvent.change(screen.getByTestId("reset-password-confirm"), {
      target: { value: "BrandNewSecurePass456!" },
    });
    fireEvent.click(screen.getByTestId("reset-password-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("reset-password-error")).toHaveTextContent(
        "invalid or has expired",
      );
    });
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
    const result = await authenticatedGet("/api/v1/auth/me");
    expect(result.ok).toBe(false);
    expect(getAccessToken()).toBeNull();
  });
});

describe("session bootstrap and refresh coordination", () => {
  it("shows restoring state and hides Log in/Register during bootstrap", async () => {
    let resolveRefresh: ((value: Response) => void) | null = null;
    const refreshGate = new Promise<Response>((resolve) => {
      resolveRefresh = resolve;
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.includes("/api/v1/auth/refresh") && method === "POST") {
          return refreshGate;
        }
        return Response.json({ error: { message: "unexpected" } }, { status: 500 });
      }),
    );

    render(
      <AuthProvider>
        <AuthHeader />
      </AuthProvider>,
    );

    expect(screen.getByTestId("auth-loading")).toHaveTextContent("Restoring session");
    expect(screen.queryByTestId("auth-anonymous")).toBeNull();
    expect(screen.queryByTestId("login-link")).toBeNull();
    expect(screen.queryByTestId("register-link")).toBeNull();

    resolveRefresh!(Response.json(authTokenResponse()));
    await waitFor(() => {
      expect(screen.getByTestId("auth-user-display")).toHaveTextContent("Demo User");
    });
  });

  it("restores authenticated state from refresh user without calling /me", async () => {
    let meCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.includes("/api/v1/auth/refresh") && method === "POST") {
          return Response.json(authTokenResponse());
        }
        if (url.includes("/api/v1/auth/me") && method === "GET") {
          meCalls += 1;
          return Response.json(demoUser());
        }
        return Response.json({ error: { message: "not found" } }, { status: 404 });
      }),
    );

    render(
      <AuthProvider>
        <AuthHeader />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("auth-user-display")).toHaveTextContent("Demo User");
    });
    expect(getAccessToken()).toBe("access-token-memory-only");
    expect(meCalls).toBe(0);
  });

  it("falls back to /me when refresh omits user", async () => {
    let meCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.includes("/api/v1/auth/refresh") && method === "POST") {
          const body = authTokenResponse() as Record<string, unknown>;
          delete body.user;
          return Response.json(body);
        }
        if (url.includes("/api/v1/auth/me") && method === "GET") {
          meCalls += 1;
          return Response.json(demoUser({ full_name: "From Me" }));
        }
        return Response.json({ error: { message: "not found" } }, { status: 404 });
      }),
    );

    render(
      <AuthProvider>
        <AuthHeader />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("auth-user-display")).toHaveTextContent("From Me");
    });
    expect(meCalls).toBe(1);
  });

  it("remount restores session through a single refresh (Strict Mode equivalent)", async () => {
    let refreshCalls = 0;
    let refreshStarted = 0;
    let releaseRefresh: (() => void) | null = null;
    const hold = new Promise<void>((resolve) => {
      releaseRefresh = resolve;
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.includes("/api/v1/auth/refresh") && method === "POST") {
          refreshStarted += 1;
          await hold;
          refreshCalls += 1;
          return Response.json(authTokenResponse());
        }
        return Response.json({ error: { message: "not found" } }, { status: 404 });
      }),
    );

    const first = render(
      <AuthProvider>
        <AuthHeader />
      </AuthProvider>,
    );
    const second = render(
      <AuthProvider>
        <AuthHeader />
      </AuthProvider>,
    );

    await waitFor(() => expect(refreshStarted).toBeGreaterThanOrEqual(1));
    releaseRefresh!();

    await waitFor(() => {
      expect(screen.getAllByTestId("auth-user-display").length).toBeGreaterThanOrEqual(1);
    });
    expect(refreshCalls).toBe(1);

    first.unmount();
    second.unmount();
  });

  it("shares one refresh across concurrent 401 retries", async () => {
    let refreshCalls = 0;
    let releaseRefresh: (() => void) | null = null;
    const hold = new Promise<void>((resolve) => {
      releaseRefresh = resolve;
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.includes("/api/v1/auth/refresh") && method === "POST") {
          refreshCalls += 1;
          await hold;
          return Response.json({
            ...authTokenResponse(),
            access_token: "refreshed-access",
          });
        }
        if (url.includes("/api/v1/protected") && method === "GET") {
          const auth = (init?.headers as Record<string, string> | undefined)?.Authorization;
          if (auth === "Bearer expired") {
            return Response.json(
              { error: { code: "invalid_access_token", message: "expired", details: [] } },
              { status: 401 },
            );
          }
          return Response.json({ ok: true });
        }
        return Response.json({ error: { message: "not found" } }, { status: 404 });
      }),
    );

    setAccessToken("expired");
    const p1 = authenticatedGet<{ ok: boolean }>("/api/v1/protected");
    const p2 = authenticatedGet<{ ok: boolean }>("/api/v1/protected");
    await waitFor(() => expect(refreshCalls).toBe(1));
    releaseRefresh!();
    const [r1, r2] = await Promise.all([p1, p2]);
    expect(r1.ok).toBe(true);
    expect(r2.ok).toBe(true);
    expect(refreshCalls).toBe(1);
    expect(getAccessToken()).toBe("refreshed-access");
  });

  it("marks anonymous only after refresh definitively fails", async () => {
    stubAuthApi({
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
      expect(screen.getByTestId("auth-anonymous")).toHaveTextContent("Not signed in");
    });
    expect(screen.getByTestId("login-link")).toBeTruthy();
    expect(screen.getByTestId("register-link")).toBeTruthy();
  });

  it("stays signed out after logout remount (refresh fails)", async () => {
    setAccessToken("access-token-memory-only");
    let loggedOut = false;
    stubAuthApi({
      me: () => Response.json(demoUser()),
      logout: () => {
        loggedOut = true;
        return Response.json({ message: "Logged out" });
      },
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

    const { unmount } = render(
      <AuthProvider>
        <AuthHeader />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("logout-button")).toBeTruthy());
    fireEvent.click(screen.getByTestId("logout-button"));
    await waitFor(() => {
      expect(screen.getByTestId("auth-anonymous")).toBeTruthy();
      expect(getAccessToken()).toBeNull();
    });
    expect(loggedOut).toBe(true);
    unmount();

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

  it("refreshSession itself is single-flight", async () => {
    let refreshCalls = 0;
    let release: (() => void) | null = null;
    const hold = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.includes("/api/v1/auth/refresh") && method === "POST") {
          refreshCalls += 1;
          await hold;
          return Response.json(authTokenResponse());
        }
        return Response.json({ error: { message: "not found" } }, { status: 404 });
      }),
    );

    const p1 = refreshSession();
    const p2 = refreshSession();
    expect(refreshCalls).toBe(1);
    release!();
    const [r1, r2] = await Promise.all([p1, p2]);
    expect(r1.ok).toBe(true);
    expect(r2.ok).toBe(true);
    expect(refreshCalls).toBe(1);
  });
});