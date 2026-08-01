import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  fetchAdminUsers: vi.fn(),
  fetchAdminTools: vi.fn(),
  fetchAdminSystem: vi.fn(),
  fetchAdminSettings: vi.fn(),
  fetchAdminAnalytics: vi.fn(),
  patchAdminTool: vi.fn(),
  patchAdminSettings: vi.fn(),
}));

import { useAuth } from "@/components/AuthProvider";
import { AdminGuard } from "@/components/admin/AdminGuard";
import { AuthHeader } from "@/components/AuthHeader";
import AdminDashboardPage from "@/app/admin/page";
import AdminUsersPage from "@/app/admin/users/page";
import AdminToolsPage from "@/app/admin/tools/page";
import AdminSystemPage from "@/app/admin/system/page";
import AdminSettingsPage from "@/app/admin/settings/page";
import AdminLoginPage from "@/app/admin/login/page";
import AdminAnalyticsPage from "@/app/admin/analytics/page";
import {
  acknowledgeAdminSession,
  fetchAdminAnalytics,
  fetchAdminDashboard,
  fetchAdminSettings,
  fetchAdminSystem,
  fetchAdminTools,
  fetchAdminUsers,
  patchAdminSettings,
  patchAdminTool,
  reportAdminLoginDenied,
} from "@/services/admin";

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
    expect(screen.getByText(/Administrator access is required/i)).toBeInTheDocument();
    expect(screen.getByTestId("admin-denied-login")).toBeInTheDocument();
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

  it("renders user table with search and role filter", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAdminUsers).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        items: [
          {
            id: "1",
            email: "a@example.com",
            full_name: "Ada",
            role: "admin",
            status: "active",
            is_email_verified: true,
            created_at: new Date().toISOString(),
            last_login_at: null,
            conversations_count: 1,
            documents_count: 0,
            memories_count: 0,
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      },
    } as never);
    render(<AdminUsersPage />);
    await waitFor(() => expect(screen.getByTestId("admin-users-page")).toBeInTheDocument());
    await user.type(screen.getByTestId("admin-users-search"), "ada");
    await user.selectOptions(screen.getByTestId("admin-users-role-filter"), "admin");
    expect(fetchAdminUsers).toHaveBeenCalled();
  });

  it("tool enable/disable requires confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAdminTools).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        tools: [
          {
            name: "calculator",
            category: "math",
            version: "1.0.0",
            description: "calc",
            enabled: true,
            registry_enabled: true,
            required_roles: ["user"],
            timeout_seconds: 30,
            confirmation_required: false,
            execution_count: 0,
            success_rate: null,
            average_duration_ms: null,
            has_configuration: false,
          },
        ],
        total: 1,
      },
    } as never);
    vi.mocked(patchAdminTool).mockResolvedValue({
      ok: true,
      status: 200,
      data: { tool: { name: "calculator", enabled: false } },
    } as never);
    render(<AdminToolsPage />);
    await waitFor(() => screen.getByTestId("admin-tool-toggle-calculator"));
    await user.click(screen.getByTestId("admin-tool-toggle-calculator"));
    expect(screen.getByTestId("admin-confirm-dialog")).toBeInTheDocument();
    await user.click(screen.getByTestId("admin-confirm-ok"));
    await waitFor(() => expect(patchAdminTool).toHaveBeenCalled());
  });

  it("system health and degraded states render", async () => {
    vi.mocked(fetchAdminSystem).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        overall: "degraded",
        components: [
          { name: "backend", status: "ok" },
          { name: "redis", status: "degraded", message: "slow" },
        ],
        ai_configuration: { provider: "ollama" },
        application: { version: "0.1.0" },
        refreshed_at: new Date().toISOString(),
        guidance: ["Check Redis"],
      },
    } as never);
    render(<AdminSystemPage />);
    await waitFor(() => expect(screen.getByTestId("admin-system-page")).toBeInTheDocument());
    expect(screen.getAllByText(/degraded/i).length).toBeGreaterThan(0);
  });

  it("settings validation error and success render", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAdminSettings).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        settings: [
          {
            key: "platform_display_name",
            value: "Cortexa",
            source: "default",
            editable: true,
          },
        ],
        runtime: {},
        unsafe_keys_blocked: ["jwt_secret_key"],
      },
    } as never);
    vi.mocked(patchAdminSettings)
      .mockResolvedValueOnce({ ok: false, status: 422, error: "Invalid setting" } as never)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        data: { settings: [], updated_keys: ["platform_display_name"] },
      } as never);
    render(<AdminSettingsPage />);
    await waitFor(() => screen.getByTestId("admin-settings-display-name"));
    await user.clear(screen.getByTestId("admin-settings-display-name"));
    await user.type(screen.getByTestId("admin-settings-display-name"), "Demo");
    await user.click(screen.getByTestId("admin-settings-save"));
    await waitFor(() => expect(screen.getByTestId("admin-settings-error")).toBeInTheDocument());
    await user.click(screen.getByTestId("admin-settings-save"));
    await waitFor(() => expect(screen.getByTestId("admin-settings-success")).toBeInTheDocument());
  });

  it("analytics range selector works", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAdminAnalytics).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        range_days: 30,
        points: [],
        totals: { new_users: 0, conversations: 0, messages: 0, tool_executions: 0 },
        unavailable: ["token_costs"],
        generated_at: new Date().toISOString(),
      },
    } as never);
    render(<AdminAnalyticsPage />);
    await waitFor(() => screen.getByTestId("admin-analytics-range"));
    await user.click(screen.getByRole("button", { name: "7d" }));
    await waitFor(() => expect(fetchAdminAnalytics).toHaveBeenCalledWith(7));
  });
});

describe("admin login page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders branded admin login and links", () => {
    mockedAuth.mockReturnValue({
      status: "unauthenticated",
      user: null,
      error: null,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      clearError: vi.fn(),
    } as never);
    render(<AdminLoginPage />);
    expect(screen.getByTestId("admin-login-page")).toBeInTheDocument();
    expect(screen.getByText("Cortexa Administration")).toBeInTheDocument();
    expect(screen.getByTestId("admin-login-security-panel")).toBeInTheDocument();
    expect(screen.getByTestId("admin-forgot-password-link")).toHaveAttribute(
      "href",
      "/forgot-password",
    );
    expect(screen.getByTestId("admin-back-to-user-login")).toHaveAttribute("href", "/login");
    expect(screen.queryByText(/demo credentials/i)).not.toBeInTheDocument();
  });

  it("submits existing auth API and acknowledges admin session", async () => {
    const user = userEvent.setup();
    const login = vi.fn().mockResolvedValue({ ok: true });
    mockedAuth.mockReturnValue({
      status: "unauthenticated",
      user: null,
      error: null,
      login,
      register: vi.fn(),
      logout: vi.fn(),
      clearError: vi.fn(),
    } as never);
    vi.mocked(acknowledgeAdminSession).mockResolvedValue({
      ok: true,
      status: 204,
      data: null,
    } as never);
    render(<AdminLoginPage />);
    await user.type(screen.getByTestId("admin-login-email"), "admin@example.com");
    await user.type(screen.getByTestId("admin-login-password"), "StrongDemoPassword123!");
    await user.click(screen.getByTestId("admin-login-submit"));
    await waitFor(() => expect(login).toHaveBeenCalled());
    expect(acknowledgeAdminSession).toHaveBeenCalled();
  });

  it("shows administrator-access-required for normal users", async () => {
    const user = userEvent.setup();
    const login = vi.fn().mockResolvedValue({ ok: true });
    const logout = vi.fn().mockResolvedValue(undefined);
    mockedAuth.mockReturnValue({
      status: "unauthenticated",
      user: null,
      error: null,
      login,
      register: vi.fn(),
      logout,
      clearError: vi.fn(),
    } as never);
    vi.mocked(acknowledgeAdminSession).mockResolvedValue({
      ok: false,
      status: 403,
      error: "Forbidden",
    } as never);
    vi.mocked(reportAdminLoginDenied).mockResolvedValue({
      ok: true,
      status: 204,
      data: null,
    } as never);
    render(<AdminLoginPage />);
    await user.type(screen.getByTestId("admin-login-email"), "user@example.com");
    await user.type(screen.getByTestId("admin-login-password"), "StrongDemoPassword123!");
    await user.click(screen.getByTestId("admin-login-submit"));
    await waitFor(() =>
      expect(screen.getByTestId("admin-login-error")).toHaveTextContent(
        /Administrator access is required/i,
      ),
    );
    expect(logout).toHaveBeenCalled();
  });

  it("shows generic invalid credentials", async () => {
    const user = userEvent.setup();
    const login = vi.fn().mockResolvedValue({ ok: false, error: "Invalid email or password" });
    mockedAuth.mockReturnValue({
      status: "unauthenticated",
      user: null,
      error: null,
      login,
      register: vi.fn(),
      logout: vi.fn(),
      clearError: vi.fn(),
    } as never);
    render(<AdminLoginPage />);
    await user.type(screen.getByTestId("admin-login-email"), "x@example.com");
    await user.type(screen.getByTestId("admin-login-password"), "StrongDemoPassword123!");
    await user.click(screen.getByTestId("admin-login-submit"));
    await waitFor(() =>
      expect(screen.getByTestId("admin-login-error")).toHaveTextContent(
        /Invalid email or password/i,
      ),
    );
  });

  it("shows loading state while signing in", async () => {
    const user = userEvent.setup();
    let resolveLogin: (value: { ok: true }) => void = () => undefined;
    const login = vi.fn().mockImplementation(
      () =>
        new Promise<{ ok: true }>((resolve) => {
          resolveLogin = resolve;
        }),
    );
    mockedAuth.mockReturnValue({
      status: "unauthenticated",
      user: null,
      error: null,
      login,
      register: vi.fn(),
      logout: vi.fn(),
      clearError: vi.fn(),
    } as never);
    vi.mocked(acknowledgeAdminSession).mockResolvedValue({
      ok: true,
      status: 204,
      data: null,
    } as never);
    render(<AdminLoginPage />);
    await user.type(screen.getByTestId("admin-login-email"), "admin@example.com");
    await user.type(screen.getByTestId("admin-login-password"), "StrongDemoPassword123!");
    await user.click(screen.getByTestId("admin-login-submit"));
    expect(screen.getByTestId("admin-login-submit")).toHaveTextContent(/Signing in/i);
    resolveLogin({ ok: true });
    await waitFor(() => expect(acknowledgeAdminSession).toHaveBeenCalled());
  });
});
