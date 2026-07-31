import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import MemoriesPage from "@/app/memories/page";
import { MemoryActivity } from "@/components/memory/MemoryActivity";
import { AuthProvider } from "@/components/AuthProvider";
import { clearAccessToken, setAccessToken } from "@/lib/auth-token";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/memories",
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  clearAccessToken();
});

beforeEach(() => {
  clearAccessToken();
});

function demoUser(overrides: Record<string, unknown> = {}) {
  return {
    id: "user-1",
    email: "mem@example.com",
    full_name: "Memory User",
    role: "user",
    status: "active",
    is_email_verified: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    last_login_at: null,
    ...overrides,
  };
}

function authTokenResponse(accessToken = "access-token-memory-only") {
  return {
    access_token: accessToken,
    token_type: "bearer",
    expires_in: 900,
    user: demoUser(),
  };
}

const sampleMemory = {
  id: "mem-1",
  category: "preference",
  status: "active",
  title: "Python preference",
  content: "The user prefers Python examples.",
  source: "explicit_user_request",
  confidence: "high",
  importance: 0.8,
  confirmation_required: false,
  confirmed_at: "2026-07-31T00:00:00Z",
  last_used_at: null,
  use_count: 0,
  expires_at: null,
  archived_at: null,
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:00:00Z",
  version: 1,
  source_conversation_id: null,
};

const proposedMemory = {
  ...sampleMemory,
  id: "mem-2",
  status: "proposed",
  title: "Suggested preference",
};

const archivedMemory = {
  ...sampleMemory,
  id: "mem-3",
  status: "archived",
  title: "Old preference",
};

const defaultSettings = {
  memory_enabled: true,
  automatic_extraction_enabled: false,
  suggestions_enabled: true,
  require_confirmation: true,
  include_memories_in_chat: true,
  maximum_active_memories: 100,
  default_expiration_days: null,
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:00:00Z",
};

function mockFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    return handler(url, init);
  }) as unknown as typeof fetch;
}

describe("memories page", () => {
  beforeEach(() => {
    setAccessToken("access-token-memory-only");
  });

  it("requires authentication", async () => {
    clearAccessToken();
    mockFetch(async (url) => {
      if (url.includes("/api/v1/auth/refresh")) {
        return new Response(JSON.stringify({ error: { message: "Unauthorized" } }), {
          status: 401,
        });
      }
      return new Response("{}", { status: 404 });
    });
    render(
      <AuthProvider>
        <MemoriesPage />
      </AuthProvider>,
    );
    await waitFor(() => {
      expect(screen.getByText(/Loading/i)).toBeInTheDocument();
    });
  });

  it("renders active, proposed, and archived memories with settings", async () => {
    mockFetch(async (url, init) => {
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/v1/auth/me") && method === "GET") {
        return new Response(JSON.stringify(demoUser()), { status: 200 });
      }
      if (url.includes("/api/v1/auth/refresh") && method === "POST") {
        return new Response(JSON.stringify(authTokenResponse()), { status: 200 });
      }
      if (url.includes("/api/v1/memory-settings") && method === "GET") {
        return new Response(JSON.stringify(defaultSettings), { status: 200 });
      }
      if (url.includes("/api/v1/memories") && method === "GET") {
        const status = new URL(url, "http://localhost").searchParams.get("status");
        let items = [sampleMemory, proposedMemory, archivedMemory];
        if (status === "active") items = [sampleMemory];
        if (status === "proposed") items = [proposedMemory];
        if (status === "archived") items = [archivedMemory];
        return new Response(
          JSON.stringify({
            items,
            total: items.length,
            limit: 20,
            offset: 0,
          }),
          { status: 200 },
        );
      }
      return new Response("{}", { status: 404 });
    });

    render(
      <AuthProvider>
        <MemoriesPage />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("memories-page")).toBeInTheDocument();
      expect(screen.getByTestId("memory-settings")).toBeInTheDocument();
    });
    expect(screen.getByText("Your AI Memory")).toBeInTheDocument();
    expect(screen.getByTestId("memory-privacy-notice")).toBeInTheDocument();
    expect(screen.getByTestId("setting-automatic-extraction")).not.toBeChecked();
    expect(screen.getByText("Python preference")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("memory-tab-proposed"));
    await waitFor(() => {
      expect(screen.getByText("Suggested preference")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("memory-tab-archived"));
    await waitFor(() => {
      expect(screen.getByText("Old preference")).toBeInTheDocument();
    });
  });

  it("confirm and reject actions work", async () => {
    let confirmed = false;
    mockFetch(async (url, init) => {
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/v1/auth/me") && method === "GET") {
        return new Response(JSON.stringify(demoUser()), { status: 200 });
      }
      if (url.includes("/api/v1/auth/refresh") && method === "POST") {
        return new Response(JSON.stringify(authTokenResponse()), { status: 200 });
      }
      if (url.includes("/api/v1/memory-settings")) {
        return new Response(JSON.stringify(defaultSettings), { status: 200 });
      }
      if (url.includes("/confirm") && method === "POST") {
        confirmed = true;
        return new Response(JSON.stringify({ ...proposedMemory, status: "active" }), {
          status: 200,
        });
      }
      if (url.includes("/api/v1/memories")) {
        return new Response(
          JSON.stringify({
            items: confirmed
              ? [{ ...proposedMemory, status: "active" }]
              : [proposedMemory],
            total: 1,
            limit: 20,
            offset: 0,
          }),
          { status: 200 },
        );
      }
      return new Response("{}", { status: 404 });
    });

    render(
      <AuthProvider>
        <MemoriesPage />
      </AuthProvider>,
    );
    fireEvent.click(await screen.findByTestId("memory-tab-proposed"));
    await waitFor(() => expect(screen.getByTestId("memory-confirm")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("memory-confirm"));
    await waitFor(() => expect(confirmed).toBe(true));
  });
});

describe("memory activity chat indicators", () => {
  it("shows retrieval count and proposal card without memory ids", () => {
    render(
      <MemoryActivity
        activity={{
          retrieving: false,
          count: 2,
          references: [
            { title: "Python preference", category: "preference" },
            { title: "Project stack", category: "project" },
          ],
          proposed: {
            title: "Preferred language",
            category: "preference",
            reason: "May improve future code examples",
          },
          savedMessage: "Preference saved",
          forgottenMessage: "Memory removed",
        }}
      />,
    );
    expect(screen.getByTestId("memory-activity")).toBeInTheDocument();
    expect(screen.getByText("2 approved memories applied")).toBeInTheDocument();
    expect(screen.getByTestId("memory-proposal-card")).toBeInTheDocument();
    expect(screen.getByText("Preference saved")).toBeInTheDocument();
    expect(screen.getByText("Memory removed")).toBeInTheDocument();
    expect(screen.queryByText(/mem-/i)).not.toBeInTheDocument();
  });

  it("shows disabled state for memory-off conversations", () => {
    render(<MemoryActivity activity={{ enabled: false }} />);
    expect(screen.getByTestId("memory-activity-disabled")).toBeInTheDocument();
  });
});
