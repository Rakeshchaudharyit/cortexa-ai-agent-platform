import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UPCOMING_CAPABILITIES } from "@/components/CapabilityCard";
import { PlatformCapabilities } from "@/components/PlatformCapabilities";
import { SystemStatusPanel } from "@/components/SystemStatusPanel";
import HomePage from "@/app/page";
import { AuthProvider } from "@/components/AuthProvider";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function stubBackend(handlers: {
  health?: () => Response;
  ready?: () => Response;
  info?: () => Response;
  llm?: () => Response;
  embeddings?: () => Response;
  failAll?: boolean;
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      if (handlers.failAll) {
        throw new TypeError("Failed to fetch");
      }
      const url = String(input);
      if (url.includes("/api/v1/auth/refresh")) {
        return Response.json(
          { error: { code: "invalid_refresh_token", message: "No session", details: [] } },
          { status: 401 },
        );
      }
      if (url.endsWith("/health") || url.includes("/health?")) {
        return (
          handlers.health?.() ??
          Response.json({
            status: "ok",
            service: "backend",
            version: "0.1.0",
            environment: "development",
          })
        );
      }
      if (url.includes("/ready")) {
        return (
          handlers.ready?.() ??
          Response.json({
            status: "ready",
            checks: {
              database: { status: "ok" },
              redis: { status: "ok" },
            },
          })
        );
      }
      if (url.includes("/api/v1/llm/status")) {
        return (
          handlers.llm?.() ??
          Response.json({
            provider: "ollama",
            model: "qwen2.5:7b",
            provider_reachable: true,
            model_available: false,
            status: "model_unavailable",
            message:
              "Ollama is reachable but the configured model is not installed. Pull it manually before generating.",
          })
        );
      }
      if (url.includes("/api/v1/embeddings/status")) {
        return (
          handlers.embeddings?.() ??
          Response.json({
            provider: "ollama",
            model: "nomic-embed-text",
            provider_reachable: true,
            model_available: true,
            configured_dimension: 768,
            status: "ready",
            message: "Embedding model available",
          })
        );
      }
      return (
        handlers.info?.() ??
        Response.json({
          name: "Cortexa AI Agent Platform",
          version: "0.1.0",
          environment: "development",
          api_version: "v1",
          features: {
            ollama: true,
            auth: true,
            rag: true,
            memory: true,
            tools: true,
            voice: false,
          },
        })
      );
    }),
  );
}

describe("SystemStatusPanel", () => {
  it("renders verified status when backend is healthy and ready", async () => {
    stubBackend({});
    render(<SystemStatusPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("status-message")).toHaveTextContent(
        "Backend is alive and required dependencies are ready.",
      );
    });

    expect(screen.getByTestId("feature-flags")).toHaveTextContent("ollama=true");
    expect(screen.getByTestId("feature-flags")).toHaveTextContent("auth=true");
    expect(screen.getByTestId("feature-flags")).toHaveTextContent("rag=true");
    expect(screen.getByTestId("feature-flags")).toHaveTextContent("tools=true");
    expect(screen.getByTestId("llm-status-section")).toBeTruthy();
    expect(screen.getByTestId("status-configured-model")).toHaveTextContent("qwen2.5:7b");
    expect(screen.getByTestId("status-model-available")).toHaveTextContent("Not pulled yet");
    expect(screen.getByTestId("status-agent-tools")).toHaveTextContent("Available");
    expect(screen.getByTestId("status-rag-vector-storage")).toHaveTextContent("Available");
    expect(screen.getAllByTestId("capability-status-badge")).toHaveLength(
      UPCOMING_CAPABILITIES.length,
    );
  });

  it("handles backend unavailable without crashing", async () => {
    stubBackend({ failAll: true });
    render(<SystemStatusPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("status-message")).toHaveTextContent("Backend unavailable");
    });
    expect(screen.getByTestId("status-backend-api")).toHaveTextContent("Unavailable");
  });

  it("handles readiness failure state", async () => {
    stubBackend({
      ready: () =>
        Response.json(
          {
            status: "not_ready",
            checks: {
              database: { status: "ok" },
              redis: { status: "error", message: "Redis unavailable" },
            },
          },
          { status: 503 },
        ),
    });

    render(<SystemStatusPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("status-message")).toHaveTextContent(
        "Backend is alive; one or more dependencies are unavailable.",
      );
    });
    expect(screen.getByTestId("status-redis")).toHaveTextContent("Redis unavailable");
    expect(screen.getByTestId("status-database")).toHaveTextContent("Healthy");
  });

  it("marks upcoming capabilities as coming later", async () => {
    stubBackend({ failAll: true });
    render(<SystemStatusPanel />);
    await waitFor(() => {
      expect(screen.getByTestId("status-message")).toHaveTextContent("Backend unavailable");
    });
    expect(screen.getAllByTestId("capability-card")).toHaveLength(UPCOMING_CAPABILITIES.length);
    for (const badge of screen.getAllByTestId("capability-status-badge")) {
      expect(badge).toHaveTextContent("Coming later");
    }
  });

  it("renders safely when one service is unavailable", async () => {
    stubBackend({
      ready: () =>
        Response.json(
          {
            status: "not_ready",
            checks: {
              database: { status: "error", message: "Database unavailable" },
              redis: { status: "ok" },
            },
          },
          { status: 503 },
        ),
    });
    render(<SystemStatusPanel />);
    await waitFor(() => {
      expect(screen.getByTestId("status-database")).toHaveTextContent("Database unavailable");
    });
    expect(screen.getByTestId("status-redis")).toHaveTextContent("Healthy");
    expect(screen.getByTestId("status-backend-api")).toHaveTextContent("Healthy");
  });
});

describe("PlatformCapabilities", () => {
  it("renders Agent Tools capability card", async () => {
    stubBackend({});
    render(<PlatformCapabilities />);
    await waitFor(() => {
      expect(screen.getByTestId("capability-agent-tools")).toBeTruthy();
    });
    expect(screen.getByTestId("capability-agent-tools")).toHaveTextContent("Agent Tools");
    expect(screen.getByTestId("capability-tool-auditing")).toHaveTextContent("Execution History");
  });
});

describe("HomePage Phase 6 status", () => {
  it("shows Phase 6 milestone and no Phase 4 copy", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/auth/refresh")) {
          return Response.json({
            user: {
              id: "11111111-1111-1111-1111-111111111111",
              email: "demo@example.com",
              full_name: "Demo User",
              role: "user",
              status: "active",
              is_email_verified: false,
              created_at: "2026-07-28T00:00:00Z",
              last_login_at: null,
            },
            access_token: "access-token",
            token_type: "bearer",
            expires_in: 900,
            access_token_expires_at: "2026-07-28T00:15:00Z",
          });
        }
        if (url.includes("/api/v1/auth/me")) {
          return Response.json({
            id: "11111111-1111-1111-1111-111111111111",
            email: "demo@example.com",
            full_name: "Demo User",
            role: "user",
            status: "active",
            is_email_verified: false,
            created_at: "2026-07-28T00:00:00Z",
            last_login_at: null,
          });
        }
        if (url.includes("/api/v1/documents")) {
          return Response.json({ items: [], total: 0, limit: 50, offset: 0 });
        }
        if (url.endsWith("/health") || url.includes("/health?")) {
          return Response.json({
            status: "ok",
            service: "backend",
            version: "0.1.0",
            environment: "development",
          });
        }
        if (url.includes("/ready")) {
          return Response.json({
            status: "ready",
            checks: {
              database: { status: "ok" },
              redis: { status: "ok" },
            },
          });
        }
        if (url.includes("/api/v1/llm/status")) {
          return Response.json({
            provider: "ollama",
            model: "qwen2.5:7b",
            provider_reachable: true,
            model_available: true,
            status: "ready",
            message: "Model available",
          });
        }
        if (url.includes("/api/v1/embeddings/status")) {
          return Response.json({
            provider: "ollama",
            model: "nomic-embed-text",
            provider_reachable: true,
            model_available: true,
            configured_dimension: 768,
            status: "ready",
            message: "Embedding model available",
          });
        }
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
            tools: true,
            voice: false,
          },
        });
      }),
    );

    render(
      <AuthProvider>
        <HomePage />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("phase-badge")).toHaveTextContent("Phase 6 — Agent Tools");
    });

    expect(screen.getByText("Current milestone: Agent Tools & Function Calling")).toBeTruthy();
    expect(screen.getByTestId("platform-status-badge")).toHaveTextContent(
      "Platform status: Development-ready",
    );
    expect(screen.queryByText(/Phase 4/i)).toBeNull();

    await waitFor(() => {
      expect(screen.getByTestId("quick-action-tools").getAttribute("href")).toBe("/tools");
    });
    expect(screen.getByTestId("agent-tools-overview")).toBeTruthy();
    expect(screen.getByTestId("capabilities-summary")).toBeTruthy();
    expect(screen.getByTestId("capability-agent-tools")).toBeTruthy();

    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/cortexa_agent(_test)?/i);
    expect(body).not.toMatch(/POSTGRES_PASSWORD|REDIS_PASSWORD|password\s*=/i);
  });
});
