import { render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

beforeAll(() => {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
});

vi.mock("recharts", () => {
  const Passthrough = ({ children }: { children?: unknown }) => (
    <div data-testid="chart-stub">{children as never}</div>
  );
  return {
    ResponsiveContainer: Passthrough,
    AreaChart: Passthrough,
    Area: () => null,
    BarChart: Passthrough,
    Bar: () => null,
    LineChart: Passthrough,
    Line: () => null,
    CartesianGrid: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/admin",
  useParams: () => ({ userId: "u1" }),
}));

vi.mock("@/components/AuthProvider", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/services/admin", () => ({
  fetchAdminDashboard: vi.fn(),
}));

import { useAuth } from "@/components/AuthProvider";
import { AdminGuard } from "@/components/admin/AdminGuard";
import { AuthHeader } from "@/components/AuthHeader";
import AdminDashboardPage from "@/app/admin/page";
import { fetchAdminDashboard } from "@/services/admin";

const mockedAuth = vi.mocked(useAuth);

describe("admin portal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("redirects unauthenticated users away from admin guard", async () => {
    const replace = vi.fn();
    vi.doMock("next/navigation", () => ({
      useRouter: () => ({ replace, push: vi.fn() }),
      usePathname: () => "/admin",
      useParams: () => ({ userId: "u1" }),
    }));
    mockedAuth.mockReturnValue({
      status: "unauthenticated",
      user: null,
      error: null,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      clearError: vi.fn(),
    } as never);
    render(
      <AdminGuard>
        <div>secret</div>
      </AdminGuard>,
    );
    await waitFor(() => expect(screen.queryByText("secret")).not.toBeInTheDocument());
  });

  it("denies normal users", () => {
    mockedAuth.mockReturnValue({
      status: "authenticated",
      user: {
        id: "1",
        email: "u@example.com",
        full_name: "User",
        role: "user",
        status: "active",
        is_email_verified: false,
        created_at: new Date().toISOString(),
        last_login_at: null,
      },
      error: null,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      clearError: vi.fn(),
    } as never);
    render(
      <AdminGuard>
        <div>secret</div>
      </AdminGuard>,
    );
    expect(screen.getByTestId("admin-access-denied")).toBeInTheDocument();
  });

  it("shows Admin nav for admins and hides for users", () => {
    mockedAuth.mockReturnValue({
      status: "authenticated",
      user: {
        id: "1",
        email: "a@example.com",
        full_name: "Admin",
        role: "admin",
        status: "active",
        is_email_verified: true,
        created_at: new Date().toISOString(),
        last_login_at: null,
      },
      error: null,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      clearError: vi.fn(),
    } as never);
    const { rerender } = render(<AuthHeader />);
    expect(screen.getByTestId("admin-link")).toBeInTheDocument();
    mockedAuth.mockReturnValue({
      status: "authenticated",
      user: {
        id: "2",
        email: "u@example.com",
        full_name: "User",
        role: "user",
        status: "active",
        is_email_verified: false,
        created_at: new Date().toISOString(),
        last_login_at: null,
      },
      error: null,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      clearError: vi.fn(),
    } as never);
    rerender(<AuthHeader />);
    expect(screen.queryByTestId("admin-link")).not.toBeInTheDocument();
  });

  it("renders dashboard metrics and loading skeleton", async () => {
    mockedAuth.mockReturnValue({
      status: "authenticated",
      user: { role: "admin", full_name: "A", email: "a@x.com" },
    } as never);
    vi.mocked(fetchAdminDashboard).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        metrics: [
          { key: "users_total", label: "Total users", value: 7 },
          { key: "documents_total", label: "Total documents", value: 0, unavailable: false },
        ],
        usage_trend: [],
        ai_activity: { provider: "ollama", model: "qwen" },
        document_pipeline: [],
        tool_usage: [],
        recent_activity: [],
        system_status: {
          backend: "ok",
          postgres: "ok",
          redis: "ok",
          ollama: "unknown",
          embedding_model: "nomic",
          migrations: "unknown",
          storage: "ok",
        },
        generated_at: new Date().toISOString(),
      },
    } as never);
    render(<AdminDashboardPage />);
    expect(screen.getByTestId("admin-dashboard-loading")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("admin-dashboard")).toBeInTheDocument());
    expect(screen.getAllByTestId("admin-metric-card").length).toBeGreaterThan(0);
    expect(screen.queryByText(/password_hash/i)).not.toBeInTheDocument();
  });
});
