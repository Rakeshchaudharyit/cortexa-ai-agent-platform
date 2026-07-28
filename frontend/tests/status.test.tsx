import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PLANNED_CAPABILITIES } from "@/components/CapabilityCard";
import { SystemStatusPanel } from "@/components/SystemStatusPanel";

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
  failAll?: boolean;
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      if (handlers.failAll) {
        throw new TypeError("Failed to fetch");
      }
      const url = String(input);
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
      return (
        handlers.info?.() ??
        Response.json({
          name: "Cortexa AI Agent Platform",
          version: "0.1.0",
          environment: "development",
          api_version: "v1",
          features: {
            ollama: true,
            rag: false,
            memory: false,
            tools: false,
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
    expect(screen.getByTestId("llm-status-section")).toBeTruthy();
    expect(screen.getByTestId("status-configured-model")).toHaveTextContent("qwen2.5:7b");
    expect(screen.getByTestId("status-model-available")).toHaveTextContent("Not pulled yet");
    expect(screen.getAllByTestId("coming-later-badge")).toHaveLength(
      PLANNED_CAPABILITIES.length,
    );
  });

  it("handles backend unavailable without crashing", async () => {
    stubBackend({ failAll: true });
    render(<SystemStatusPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("status-message")).toHaveTextContent("Backend unavailable");
    });
    expect(screen.getByTestId("status-backend-api")).toHaveTextContent("Unreachable");
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
    expect(screen.getByTestId("status-database")).toHaveTextContent("Reachable");
  });

  it("marks planned capabilities as coming later", async () => {
    stubBackend({ failAll: true });
    render(<SystemStatusPanel />);
    await waitFor(() => {
      expect(screen.getByTestId("status-message")).toHaveTextContent("Backend unavailable");
    });
    expect(screen.getAllByTestId("capability-card")).toHaveLength(PLANNED_CAPABILITIES.length);
    for (const badge of screen.getAllByTestId("coming-later-badge")) {
      expect(badge).toHaveTextContent("Coming later");
    }
  });
});
