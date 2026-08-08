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
          name: "Cortexa AI Knowledge Platform",
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

describe("Public portfolio landing", () => {
  it("presents the stable product story without development milestones", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/auth/refresh")) {
          return Response.json({
            error: { code: "unauthorized", message: "Not authenticated" },
          }, { status: 401 });
        }
        return Response.json({});
      }),
    );

    render(
      <AuthProvider>
        <HomePage />
      </AuthProvider>,
    );

    expect(screen.getByText("Private knowledge.")).toBeTruthy();
    expect(screen.getByText("Grounded answers.")).toBeTruthy();
    expect(screen.getByText("Measurable AI quality.")).toBeTruthy();
    expect(screen.getByText("Built beyond the chatbot demo.")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Explore product tour/i }).getAttribute("href")).toBe("/demo");

    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/Phase \d|milestone/i);
    expect(body).not.toMatch(/POSTGRES_PASSWORD|REDIS_PASSWORD|password\s*=/i);
  });
});
