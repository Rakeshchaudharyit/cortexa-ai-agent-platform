import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

beforeAll(() => {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
});

afterEach(() => {
  cleanup();
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
  useParams: () => ({ userId: "u-target" }),
}));

vi.mock("@/components/AuthProvider", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/services/admin", () => ({
  fetchAdminDashboard: vi.fn(),
  fetchAdminUsers: vi.fn(),
  fetchAdminUser: vi.fn(),
  fetchAdminTools: vi.fn(),
  fetchAdminSystem: vi.fn(),
  fetchAdminSettings: vi.fn(),
  fetchAdminAnalytics: vi.fn(),
  fetchAdminDocuments: vi.fn(),
  fetchAdminConversations: vi.fn(),
  fetchAdminMemories: vi.fn(),
  patchAdminTool: vi.fn(),
  patchAdminSettings: vi.fn(),
  patchAdminUser: vi.fn(),
  deactivateAdminUser: vi.fn(),
  activateAdminUser: vi.fn(),
  deleteAdminUser: vi.fn(),
  fetchUserDeletionImpact: vi.fn(),
  fetchDocumentDeletionImpact: vi.fn(),
  deleteAdminDocument: vi.fn(),
  archiveAdminConversation: vi.fn(),
  deleteAdminConversation: vi.fn(),
  fetchConversationDeletionImpact: vi.fn(),
  archiveAdminMemory: vi.fn(),
  deleteAdminMemory: vi.fn(),
  fetchMemoryDeletionImpact: vi.fn(),
  resetAdminToolConfiguration: vi.fn(),
  resetAdminSetting: vi.fn(),
  acknowledgeAdminSession: vi.fn(),
  reportAdminLoginDenied: vi.fn(),
  revokeAdminUserSessions: vi.fn(),
}));

import { useAuth } from "@/components/AuthProvider";
import { AdminGuard } from "@/components/admin/AdminGuard";
import { AuthHeader } from "@/components/AuthHeader";
import AdminDashboardPage from "@/app/admin/page";
import AdminUsersPage from "@/app/admin/users/page";
import AdminUserDetailPage from "@/app/admin/users/[userId]/page";
import AdminToolsPage from "@/app/admin/tools/page";
import AdminSystemPage from "@/app/admin/system/page";
import AdminSettingsPage from "@/app/admin/settings/page";
import AdminLoginPage from "@/app/admin/login/page";
import AdminDocumentsPage from "@/app/admin/documents/page";
import AdminConversationsPage from "@/app/admin/conversations/page";
import AdminMemoriesPage from "@/app/admin/memories/page";
import {
  acknowledgeAdminSession,
  fetchAdminConversations,
  fetchAdminDashboard,
  fetchAdminDocuments,
  fetchAdminMemories,
  fetchAdminSettings,
  fetchAdminSystem,
  fetchAdminTools,
  fetchAdminUser,
  fetchAdminUsers,
  fetchDocumentDeletionImpact,
  fetchUserDeletionImpact,
  patchAdminSettings,
  patchAdminTool,
  reportAdminLoginDenied,
} from "@/services/admin";

const mockedAuth = vi.mocked(useAuth);

function mockAdminAuth(overrides: Record<string, unknown> = {}) {
  mockedAuth.mockReturnValue({
    status: "authenticated",
    user: {
      id: "actor-1",
      email: "admin@example.com",
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
    ...overrides,
  } as never);
}

describe("admin portal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAdminAuth();
  });

  it("redirects unauthenticated users away from admin guard", async () => {
    mockAdminAuth({ status: "unauthenticated", user: null });
    render(
      <AdminGuard>
        <div>secret</div>
      </AdminGuard>,
    );
    await waitFor(() => expect(screen.queryByText("secret")).not.toBeInTheDocument());
  });

  it("denies normal users", () => {
    mockAdminAuth({
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
    });
    render(
      <AdminGuard>
        <div>secret</div>
      </AdminGuard>,
    );
    expect(screen.getByTestId("admin-access-denied")).toBeInTheDocument();
    expect(screen.getByText(/Administrator access is required/i)).toBeInTheDocument();
  });

  it("shows Admin nav for admins and hides for users", () => {
    mockAdminAuth();
    const { rerender } = render(<AuthHeader />);
    expect(screen.getByTestId("admin-link")).toBeInTheDocument();
    mockAdminAuth({
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
    });
    rerender(<AuthHeader />);
    expect(screen.queryByTestId("admin-link")).not.toBeInTheDocument();
  });

  it("renders dashboard metrics and loading skeleton", async () => {
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
    await waitFor(() => expect(screen.getByTestId("admin-action-toast")).toBeInTheDocument());
    expect(screen.getByTestId("admin-action-toast").textContent).toMatch(/invalid/i);
    await user.click(screen.getByTestId("admin-settings-save"));
    await waitFor(() =>
      expect(screen.getByTestId("admin-action-toast").textContent).toMatch(/updated/i),
    );
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

describe("admin deletion UX", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAdminAuth();
  });

  it("user deletion requires typed email confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAdminUser).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        id: "u-target",
        email: "target@example.com",
        full_name: "Target",
        role: "user",
        status: "active",
        is_email_verified: true,
        created_at: new Date().toISOString(),
        last_login_at: null,
        conversations_count: 1,
        documents_count: 2,
        memories_count: 0,
        active_sessions_count: 1,
        tool_executions_count: 0,
        tool_success_count: 0,
        tool_failure_count: 0,
      },
    } as never);
    vi.mocked(fetchUserDeletionImpact).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        user_id: "u-target",
        documents: 2,
        document_chunks: 5,
        conversations: 1,
        messages: 3,
        memories: 0,
        refresh_sessions: 1,
        tool_executions: 0,
        can_delete: true,
        blocking_reason: null,
      },
    } as never);
    render(<AdminUserDetailPage />);
    await waitFor(() => screen.getByTestId("admin-user-permanent-delete"));
    await user.click(screen.getByTestId("admin-user-permanent-delete"));
    await waitFor(() => screen.getByTestId("deletion-impact-counts"));
    expect(screen.getByTestId("admin-delete-confirm")).toBeDisabled();
    await user.type(screen.getByTestId("admin-delete-email-confirm"), "target@example.com");
    await waitFor(() =>
      expect(screen.getByTestId("admin-delete-confirm")).not.toBeDisabled(),
    );
  });

  it("self-delete action unavailable on own profile", async () => {
    mockAdminAuth({
      user: {
        id: "u1",
        email: "admin@example.com",
        full_name: "Admin",
        role: "admin",
        status: "active",
        is_email_verified: true,
        created_at: new Date().toISOString(),
        last_login_at: null,
      },
    });
    vi.mocked(fetchAdminUser).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        id: "u1",
        email: "admin@example.com",
        full_name: "Admin",
        role: "admin",
        status: "active",
        is_email_verified: true,
        created_at: new Date().toISOString(),
        last_login_at: null,
        conversations_count: 0,
        documents_count: 0,
        memories_count: 0,
        active_sessions_count: 0,
        tool_executions_count: 0,
        tool_success_count: 0,
        tool_failure_count: 0,
      },
    } as never);
    render(<AdminUserDetailPage />);
    await waitFor(() => screen.getByTestId("admin-user-permanent-delete"));
    expect(screen.getByTestId("admin-user-permanent-delete")).toBeDisabled();
    expect(screen.getByTestId("admin-self-delete-blocked")).toBeInTheDocument();
  });

  it("document deletion dialog shows impact", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAdminDocuments).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        items: [
          {
            id: "d1",
            filename: "notes.txt",
            owner_id: "u1",
            owner_email: "o@example.com",
            status: "ready",
            chunk_count: 4,
            created_at: new Date().toISOString(),
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      },
    } as never);
    vi.mocked(fetchDocumentDeletionImpact).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        document_id: "d1",
        filename: "notes.txt",
        owner_id: "u1",
        owner_email: "o@example.com",
        chunk_count: 4,
        has_stored_file: true,
        can_delete: true,
        blocking_reason: null,
      },
    } as never);
    render(<AdminDocumentsPage />);
    await waitFor(() => screen.getByTestId("admin-document-delete-d1"));
    await user.click(screen.getByTestId("admin-document-delete-d1"));
    await waitFor(() => screen.getByTestId("deletion-impact-counts"));
    expect(screen.getByText(/embeddings and the stored upload/i)).toBeInTheDocument();
  });

  it("conversation archive and delete are distinct labels", async () => {
    vi.mocked(fetchAdminConversations).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        items: [
          {
            id: "c1",
            title: "Chat",
            owner_id: "u1",
            owner_email: "o@example.com",
            status: "active",
            message_count: 2,
            tool_execution_count: 0,
            created_at: new Date().toISOString(),
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      },
    } as never);
    render(<AdminConversationsPage />);
    await waitFor(() => screen.getByTestId("admin-conversation-archive-c1"));
    expect(screen.getByTestId("admin-conversation-delete-c1")).toHaveTextContent(
      /Delete permanently/i,
    );
    expect(screen.getByTestId("admin-conversation-archive-c1")).toHaveTextContent(/Archive/i);
  });

  it("memory delete says delete and redact", async () => {
    vi.mocked(fetchAdminMemories).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        items: [
          {
            id: "m1",
            title: "Pref",
            owner_id: "u1",
            owner_email: "o@example.com",
            category: "preference",
            status: "active",
            source: "explicit_user_request",
            created_at: new Date().toISOString(),
            use_count: 0,
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      },
    } as never);
    render(<AdminMemoriesPage />);
    await waitFor(() => screen.getByTestId("admin-memory-delete-m1"));
    expect(screen.getByTestId("admin-memory-delete-m1")).toHaveTextContent(/Delete and redact/i);
  });

  it("tool action says reset configuration when override exists", async () => {
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
            enabled: false,
            registry_enabled: true,
            required_roles: ["user"],
            timeout_seconds: 30,
            confirmation_required: false,
            execution_count: 0,
            success_rate: null,
            average_duration_ms: null,
            has_configuration: true,
          },
        ],
        total: 1,
      },
    } as never);
    render(<AdminToolsPage />);
    await waitFor(() => screen.getByTestId("admin-tool-reset-calculator"));
    expect(screen.getByTestId("admin-tool-reset-calculator")).toHaveTextContent(
      /Reset configuration/i,
    );
  });

  it("setting action says reset to default", async () => {
    vi.mocked(fetchAdminSettings).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        settings: [
          {
            key: "platform_display_name",
            value: "Demo",
            source: "override",
            editable: true,
          },
        ],
        runtime: {},
        unsafe_keys_blocked: [],
      },
    } as never);
    render(<AdminSettingsPage />);
    await waitFor(() => screen.getByTestId("admin-settings-reset-platform_display_name"));
    expect(screen.getByTestId("admin-settings-reset-platform_display_name")).toHaveTextContent(
      /Reset to default/i,
    );
  });
});
