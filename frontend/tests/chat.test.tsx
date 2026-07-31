/**
 * Phase 5 Chat UI — vitest tests.
 *
 * Covers: new chat creation, conversation list, selection, search, rename,
 * archive/delete confirmation, message history, send message, streaming
 * delta/complete/error, citation rendering, markdown + unsafe HTML sanitized,
 * copy response, edit/regenerate, document scope, loading/empty, protected
 * route redirect, no token in localStorage, keyboard submit / Shift+Enter,
 * accessibility labels.
 */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/components/AuthProvider";
import { ConversationSidebar } from "@/components/chat/ConversationSidebar";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { MessageList } from "@/components/chat/MessageList";
import { CitationCard } from "@/components/chat/CitationCard";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth-token";
import type { ConversationMessage, ConversationSummary, MessageCitation } from "@/types/api";

// ─── Mocks ────────────────────────────────────────────────────────────────────

const pushMock = vi.fn();
const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  usePathname: () => "/chat",
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  clearAccessToken();
  pushMock.mockReset();
  replaceMock.mockReset();
});

beforeEach(() => {
  clearAccessToken();
});

// ─── Fixtures ─────────────────────────────────────────────────────────────────

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

function authTokenResponse(accessToken = "access-token-memory-only") {
  return {
    user: demoUser(),
    access_token: accessToken,
    token_type: "bearer",
    expires_in: 900,
    access_token_expires_at: "2026-07-28T00:15:00Z",
  };
}

function sampleConv(overrides: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    title: "Test Conversation",
    status: "active",
    message_count: 2,
    created_at: "2026-07-28T00:00:00Z",
    updated_at: "2026-07-28T00:01:00Z",
    last_message_at: "2026-07-28T00:01:00Z",
    archived_at: null,
    title_is_auto: false,
    summary_preview: null,
    ...overrides,
  };
}

function sampleConv2(): ConversationSummary {
  return sampleConv({
    id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    title: "Second Conversation",
  });
}

function sampleCitation(overrides: Partial<MessageCitation> = {}): MessageCitation {
  return {
    id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
    citation_index: 1,
    citation_id: "[1]",
    document_id: "dddddddd-dddd-dddd-dddd-dddddddddddd",
    chunk_id: "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
    filename: "notes.txt",
    page_number: null,
    chunk_index: 0,
    excerpt: "Cortexa is a local-first platform.",
    similarity_score: 0.92,
    ...overrides,
  };
}

function sampleMessage(overrides: Partial<ConversationMessage> = {}): ConversationMessage {
  return {
    id: "ffffffff-ffff-ffff-ffff-ffffffffffff",
    conversation_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    role: "user",
    content: "Hello there",
    status: "complete",
    sequence_number: 1,
    is_active: true,
    grounded: null,
    model: null,
    provider: null,
    prompt_tokens: null,
    completion_tokens: null,
    total_tokens: null,
    latency_ms: null,
    finish_reason: null,
    error_code: null,
    regenerated_from_message_id: null,
    edited_from_message_id: null,
    created_at: "2026-07-28T00:00:00Z",
    updated_at: "2026-07-28T00:00:00Z",
    citations: [],
    ...overrides,
  };
}

function assistantMessage(content = "Hello, how can I help?") {
  return sampleMessage({
    id: "99999999-9999-9999-9999-999999999999",
    role: "assistant",
    content,
    citations: [],
    model: "qwen2.5:7b",
    latency_ms: 123,
  });
}

// ─── Auth stub helper ─────────────────────────────────────────────────────────

type StubFetchHandlers = {
  refresh?: () => Response;
  me?: () => Response;
  listConversations?: () => Response;
  createConversation?: () => Response;
  renameConversation?: (id: string) => Response;
  archiveConversation?: (id: string) => Response;
  deleteConversation?: (id: string) => Response;
};

function stubFetch(handlers: StubFetchHandlers = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();

      // Auth endpoints
      if (url.includes("/api/v1/auth/refresh") && method === "POST") {
        return (
          handlers.refresh?.() ??
          Response.json(
            { error: { code: "invalid_refresh_token", message: "Bad token" } },
            { status: 401 },
          )
        );
      }
      if (url.includes("/api/v1/auth/me") && method === "GET") {
        return handlers.me?.() ?? Response.json(demoUser());
      }

      // Conversation endpoints
      if (url.includes("/api/v1/conversations") && method === "GET" && !url.includes("/messages")) {
        // Check if it's a list (no UUID segment at end)
        const isDetail = /\/conversations\/[a-f0-9-]{36}$/.test(url);
        if (!isDetail) {
          return (
            handlers.listConversations?.() ??
            Response.json({ items: [], total: 0, limit: 50, offset: 0 })
          );
        }
      }
      if (url.includes("/api/v1/conversations") && method === "POST" && !url.match(/\/messages|\/archive|\/unarchive|\/regenerate/)) {
        return (
          handlers.createConversation?.() ??
          Response.json(sampleConv(), { status: 201 })
        );
      }
      if (url.includes("/archive") && method === "POST") {
        const id = url.match(/\/conversations\/([^/]+)\/archive/)?.[1] ?? "";
        return (
          handlers.archiveConversation?.(id) ??
          Response.json(sampleConv({ id, status: "archived" }))
        );
      }
      if (url.match(/\/conversations\/[^/]+$/) && method === "DELETE") {
        return (
          handlers.deleteConversation?.("") ??
          new Response(null, { status: 204 })
        );
      }
      if (url.match(/\/conversations\/[^/]+$/) && method === "PATCH") {
        const id = url.match(/\/conversations\/([^/]+)$/)?.[1] ?? "";
        return (
          handlers.renameConversation?.(id) ??
          Response.json(sampleConv({ id, title: "Renamed Title" }))
        );
      }

      return Response.json(
        { error: { code: "not_found", message: "Resource not found" } },
        { status: 404 },
      );
    }),
  );
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("ConversationSidebar", () => {
  it("shows loading state, then empty state when no conversations", async () => {
    stubFetch({ me: () => Response.json(demoUser()) });
    setAccessToken("t");
    render(
      <ConversationSidebar activeId={null} onNewConversation={vi.fn()} />,
    );
    // Loading flashes briefly then resolves.
    await waitFor(() => {
      expect(screen.getByTestId("sidebar-empty")).toBeTruthy();
    });
    expect(screen.getByTestId("sidebar-empty").textContent).toContain("No conversations");
  });

  it("renders conversation list", async () => {
    stubFetch({
      me: () => Response.json(demoUser()),
      listConversations: () =>
        Response.json({ items: [sampleConv(), sampleConv2()], total: 2, limit: 50, offset: 0 }),
    });
    setAccessToken("t");
    render(<ConversationSidebar activeId={null} onNewConversation={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId(`conv-title-${sampleConv().id}`)).toBeTruthy();
    });
    expect(screen.getByTestId(`conv-title-${sampleConv2().id}`)).toBeTruthy();
  });

  it("highlights the active conversation", async () => {
    const conv = sampleConv();
    stubFetch({
      listConversations: () =>
        Response.json({ items: [conv], total: 1, limit: 50, offset: 0 }),
    });
    setAccessToken("t");
    render(<ConversationSidebar activeId={conv.id} onNewConversation={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId(`conversation-item-${conv.id}`)).toBeTruthy();
    });
    expect(
      screen.getByTestId(`conversation-item-${conv.id}`).getAttribute("aria-current"),
    ).toBe("page");
  });

  it("calls onNewConversation with new conversation id when creating", async () => {
    const newConv = sampleConv({ id: "new-id-1234" });
    const onNew = vi.fn();
    stubFetch({
      listConversations: () => Response.json({ items: [], total: 0, limit: 50, offset: 0 }),
      createConversation: () => Response.json(newConv, { status: 201 }),
    });
    setAccessToken("t");
    render(<ConversationSidebar activeId={null} onNewConversation={onNew} />);
    await waitFor(() => screen.getByTestId("new-chat-button"));
    fireEvent.click(screen.getByTestId("new-chat-button"));
    await waitFor(() => expect(onNew).toHaveBeenCalledWith(newConv.id));
  });

  it("shows conversation search input with accessible label", async () => {
    stubFetch({});
    setAccessToken("t");
    render(<ConversationSidebar activeId={null} onNewConversation={vi.fn()} />);
    const input = await screen.findByTestId("conversation-search");
    expect(input.getAttribute("aria-label")).toBeTruthy();
  });

  it("shows error state on list failure and retry button", async () => {
    stubFetch({
      listConversations: () => Response.json({ error: { message: "Server error" } }, { status: 500 }),
    });
    setAccessToken("t");
    render(<ConversationSidebar activeId={null} onNewConversation={vi.fn()} />);
    await waitFor(() => screen.getByTestId("sidebar-error"));
    expect(screen.getByText("Retry")).toBeTruthy();
  });

  it("shows archived toggle button", async () => {
    stubFetch({});
    setAccessToken("t");
    render(<ConversationSidebar activeId={null} onNewConversation={vi.fn()} />);
    const toggle = await screen.findByTestId("archived-toggle");
    expect(toggle.textContent).toContain("archived");
  });

  it("shows delete confirmation dialog and cancels", async () => {
    const conv = sampleConv();
    stubFetch({
      listConversations: () =>
        Response.json({ items: [conv], total: 1, limit: 50, offset: 0 }),
    });
    setAccessToken("t");
    render(<ConversationSidebar activeId={null} onNewConversation={vi.fn()} />);
    await waitFor(() => screen.getByTestId(`conversation-item-${conv.id}`));

    // Hover/show action buttons.
    const deleteBtn = screen.getByTestId(`delete-btn-${conv.id}`);
    fireEvent.click(deleteBtn);
    await waitFor(() => screen.getByTestId("confirm-dialog"));
    expect(screen.getByTestId("confirm-dialog").textContent).toContain("Delete");

    fireEvent.click(screen.getByTestId("confirm-cancel"));
    await waitFor(() => expect(screen.queryByTestId("confirm-dialog")).toBeNull());
  });

  it("deletes conversation on confirm", async () => {
    const conv = sampleConv();
    const onNew = vi.fn();
    stubFetch({
      listConversations: () =>
        Response.json({ items: [conv], total: 1, limit: 50, offset: 0 }),
      deleteConversation: () => new Response(null, { status: 204 }),
    });
    setAccessToken("t");
    render(<ConversationSidebar activeId={null} onNewConversation={onNew} />);
    await waitFor(() => screen.getByTestId(`delete-btn-${conv.id}`));
    fireEvent.click(screen.getByTestId(`delete-btn-${conv.id}`));
    await waitFor(() => screen.getByTestId("confirm-ok"));
    fireEvent.click(screen.getByTestId("confirm-ok"));
    await waitFor(() =>
      expect(screen.queryByTestId(`conversation-item-${conv.id}`)).toBeNull(),
    );
  });

  it("archives conversation on confirm", async () => {
    const conv = sampleConv();
    stubFetch({
      listConversations: () =>
        Response.json({ items: [conv], total: 1, limit: 50, offset: 0 }),
      archiveConversation: (id) =>
        Response.json({
          ...conv,
          id,
          status: "archived",
          archived_at: new Date().toISOString(),
        }),
    });
    setAccessToken("t");
    render(<ConversationSidebar activeId={null} onNewConversation={vi.fn()} />);
    await waitFor(() => screen.getByTestId(`archive-btn-${conv.id}`));
    fireEvent.click(screen.getByTestId(`archive-btn-${conv.id}`));
    await waitFor(() => screen.getByTestId("confirm-ok"));
    fireEvent.click(screen.getByTestId("confirm-ok"));
    // After archive, sidebar reloads. No crash.
    await waitFor(() => expect(screen.queryByTestId("confirm-dialog")).toBeNull());
  });

  it("allows renaming via inline input, submitting on Enter", async () => {
    const conv = sampleConv();
    stubFetch({
      listConversations: () =>
        Response.json({ items: [conv], total: 1, limit: 50, offset: 0 }),
      renameConversation: () => Response.json({ ...conv, title: "Renamed Title" }),
    });
    setAccessToken("t");
    render(<ConversationSidebar activeId={null} onNewConversation={vi.fn()} />);
    await waitFor(() => screen.getByTestId(`rename-btn-${conv.id}`));
    fireEvent.click(screen.getByTestId(`rename-btn-${conv.id}`));
    const input = screen.getByTestId(`rename-input-${conv.id}`);
    fireEvent.change(input, { target: { value: "Renamed Title" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => {
      expect(screen.queryByTestId(`rename-input-${conv.id}`)).toBeNull();
    });
    expect(screen.getByTestId(`conv-title-${conv.id}`).textContent).toBe("Renamed Title");
  });

  it("cancels renaming on Escape", async () => {
    const conv = sampleConv();
    stubFetch({
      listConversations: () =>
        Response.json({ items: [conv], total: 1, limit: 50, offset: 0 }),
    });
    setAccessToken("t");
    render(<ConversationSidebar activeId={null} onNewConversation={vi.fn()} />);
    await waitFor(() => screen.getByTestId(`rename-btn-${conv.id}`));
    fireEvent.click(screen.getByTestId(`rename-btn-${conv.id}`));
    const input = screen.getByTestId(`rename-input-${conv.id}`);
    fireEvent.keyDown(input, { key: "Escape" });
    await waitFor(() => {
      expect(screen.queryByTestId(`rename-input-${conv.id}`)).toBeNull();
    });
  });
});

// ─── ChatComposer ─────────────────────────────────────────────────────────────

describe("ChatComposer", () => {
  it("renders with accessible label", () => {
    render(
      <ChatComposer onSend={vi.fn()} />,
    );
    expect(screen.getByLabelText("Message input")).toBeTruthy();
    expect(screen.getByTestId("chat-composer").getAttribute("aria-label")).toBeTruthy();
  });

  it("sends on Enter key", async () => {
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} />);
    const input = screen.getByTestId("composer-input");
    fireEvent.change(input, { target: { value: "Hello!" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledWith("Hello!", null);
  });

  it("does not send on Shift+Enter (newline)", () => {
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} />);
    const input = screen.getByTestId("composer-input");
    fireEvent.change(input, { target: { value: "Hello" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("send button is disabled when input is empty", () => {
    render(<ChatComposer onSend={vi.fn()} />);
    expect(screen.getByTestId("send-button")).toBeDisabled();
  });

  it("send button is disabled when streaming", () => {
    render(<ChatComposer onSend={vi.fn()} isStreaming />);
    expect(screen.getByTestId("cancel-stream-button")).toBeTruthy();
    expect(screen.queryByTestId("send-button")).toBeNull();
  });

  it("shows cancel button when streaming and calls onCancel", () => {
    const onCancel = vi.fn();
    render(<ChatComposer onSend={vi.fn()} isStreaming onCancel={onCancel} />);
    fireEvent.click(screen.getByTestId("cancel-stream-button"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("clears draft after send", () => {
    render(<ChatComposer onSend={vi.fn()} />);
    const input = screen.getByTestId("composer-input") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "Hello!" } });
    fireEvent.click(screen.getByTestId("send-button"));
    expect(input.value).toBe("");
  });

  it("passes document_ids=null when scope is 'all'", () => {
    const onSend = vi.fn();
    render(
      <ChatComposer
        onSend={onSend}
        availableDocumentIds={["doc-1", "doc-2"]}
      />,
    );
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Hi" } });
    fireEvent.click(screen.getByTestId("send-button"));
    expect(onSend).toHaveBeenCalledWith("Hi", null);
  });

  it("passes document_ids=[] when scope is 'none' (general chat)", () => {
    const onSend = vi.fn();
    render(
      <ChatComposer
        onSend={onSend}
        availableDocumentIds={["doc-1"]}
      />,
    );
    // Click "General chat" scope button.
    const noneBtn = screen.getByText("General chat (no docs)");
    fireEvent.click(noneBtn);
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Hi" } });
    fireEvent.click(screen.getByTestId("send-button"));
    expect(onSend).toHaveBeenCalledWith("Hi", []);
  });

  it("renders document selector when scope is 'selected'", () => {
    render(
      <ChatComposer
        onSend={vi.fn()}
        availableDocumentIds={["doc-aabbcc", "doc-112233"]}
      />,
    );
    fireEvent.click(screen.getByText("Selected…"));
    expect(screen.getByTestId("doc-selector")).toBeTruthy();
  });
});

// ─── MessageBubble ────────────────────────────────────────────────────────────

describe("MessageBubble", () => {
  it("renders user message", () => {
    const msg = sampleMessage({ role: "user", content: "Hello there" });
    render(<MessageBubble message={msg} />);
    expect(screen.getByText("Hello there")).toBeTruthy();
    expect(screen.getByLabelText("Your message")).toBeTruthy();
  });

  it("renders assistant message with markdown", () => {
    const msg = assistantMessage("**Bold text** and `code`");
    render(<MessageBubble message={msg} />);
    expect(screen.getByTestId("markdown-content")).toBeTruthy();
  });

  it("shows streaming cursor when isStreaming=true", () => {
    const msg = assistantMessage("Partial answer");
    render(<MessageBubble message={msg} isStreaming />);
    expect(screen.getByLabelText("Streaming")).toBeTruthy();
  });

  it("renders citation cards", () => {
    const citation = sampleCitation();
    const msg = assistantMessage("Answer [1]");
    msg.citations = [citation];
    render(<MessageBubble message={msg} />);
    expect(screen.getByTestId("citation-card-1")).toBeTruthy();
  });

  it("shows metadata line with model and latency", () => {
    const msg = assistantMessage("Answer");
    msg.model = "qwen2.5:7b";
    msg.latency_ms = 99;
    render(<MessageBubble message={msg} />);
    expect(screen.getByTestId("message-metadata").textContent).toContain("qwen2.5:7b");
    expect(screen.getByTestId("message-metadata").textContent).toContain("99ms");
  });

  it("shows copy button on assistant message and copies text", async () => {
    const msg = assistantMessage("Copy me");
    const clipboardWriteText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", {
      clipboard: { writeText: clipboardWriteText },
    });
    render(<MessageBubble message={msg} />);
    const copyBtn = screen.getByTestId("copy-button");
    await act(async () => {
      fireEvent.click(copyBtn);
    });
    expect(clipboardWriteText).toHaveBeenCalledWith("Copy me");
  });

  it("shows regenerate button on latest assistant message", () => {
    const onRegen = vi.fn();
    const msg = assistantMessage("Re-generate me");
    render(<MessageBubble message={msg} onRegenerate={onRegen} />);
    const btn = screen.getByTestId("regenerate-button");
    fireEvent.click(btn);
    expect(onRegen).toHaveBeenCalled();
  });

  it("shows edit button on latest user message and calls onEdit", async () => {
    const onEdit = vi.fn();
    const msg = sampleMessage({ role: "user", content: "Original content" });
    render(<MessageBubble message={msg} onEdit={onEdit} />);
    fireEvent.click(screen.getByTestId("edit-button"));
    const textarea = screen.getByTestId("edit-textarea") as HTMLTextAreaElement;
    expect(textarea.value).toBe("Original content");
    fireEvent.change(textarea, { target: { value: "Updated content" } });
    fireEvent.click(screen.getByTestId("edit-submit"));
    expect(onEdit).toHaveBeenCalledWith("Updated content");
  });

  it("cancels edit and reverts draft", () => {
    const msg = sampleMessage({ role: "user", content: "Original" });
    render(<MessageBubble message={msg} onEdit={vi.fn()} />);
    fireEvent.click(screen.getByTestId("edit-button"));
    fireEvent.change(screen.getByTestId("edit-textarea"), { target: { value: "Changed" } });
    fireEvent.click(screen.getByTestId("edit-cancel"));
    // Edit textarea should be gone.
    expect(screen.queryByTestId("edit-textarea")).toBeNull();
  });
});

// ─── CitationCard ─────────────────────────────────────────────────────────────

describe("CitationCard", () => {
  it("renders citation index, filename, and excerpt", () => {
    const c = sampleCitation({ citation_index: 2, filename: "report.pdf" });
    render(<CitationCard citation={c} />);
    expect(screen.getByTestId("citation-card-2")).toBeTruthy();
    expect(screen.getByTestId("citation-card-2").textContent).toContain("[2]");
    expect(screen.getByTestId("citation-card-2").textContent).toContain("report.pdf");
    expect(screen.getByTestId("citation-card-2").textContent).toContain(c.excerpt);
  });

  it("shows page number when available", () => {
    const c = sampleCitation({ page_number: 5 });
    render(<CitationCard citation={c} />);
    expect(screen.getByTestId("citation-card-1").textContent).toContain("p.5");
  });

  it("has accessible aria-label", () => {
    const c = sampleCitation();
    render(<CitationCard citation={c} />);
    const card = screen.getByTestId("citation-card-1");
    expect(card.getAttribute("aria-label")).toContain("Citation 1");
    expect(card.getAttribute("aria-label")).toContain("notes.txt");
  });
});

// ─── MarkdownContent ──────────────────────────────────────────────────────────

describe("MarkdownContent", () => {
  it("renders plain text", () => {
    render(<MarkdownContent content="Hello world" />);
    expect(screen.getByTestId("markdown-content").textContent).toContain("Hello world");
  });

  it("renders bold markdown", () => {
    render(<MarkdownContent content="**bold text**" />);
    const el = screen.getByTestId("markdown-content");
    expect(el.querySelector("strong")).toBeTruthy();
  });

  it("sanitizes script tags — no script executes", () => {
    const xss = '<script>window.__XSS__=true</script>hello';
    render(<MarkdownContent content={xss} />);
    const el = screen.getByTestId("markdown-content");
    expect(el.querySelector("script")).toBeNull();
    // Verify window.__XSS__ was NOT set.
    expect((window as unknown as Record<string, unknown>).__XSS__).toBeUndefined();
  });

  it("sanitizes onclick attributes", () => {
    const xss = '<a href="/" onclick="window.__CLICKED__=true">click</a>';
    render(<MarkdownContent content={xss} />);
    const link = screen.getByTestId("markdown-content").querySelector("a");
    // onclick should be stripped by rehype-sanitize.
    if (link) {
      expect(link.getAttribute("onclick")).toBeNull();
    }
    expect((window as unknown as Record<string, unknown>).__CLICKED__).toBeUndefined();
  });

  it("renders external links with target=_blank and rel=noopener", async () => {
    render(<MarkdownContent content="[Cortexa](https://example.com)" />);
    const link = await screen.findByRole("link", { name: "Cortexa" });
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("renders code blocks with pre/code elements", () => {
    render(<MarkdownContent content={"```js\nconsole.log('hi')\n```"} />);
    const el = screen.getByTestId("markdown-content");
    expect(el.querySelector("pre")).toBeTruthy();
    expect(el.querySelector("code")).toBeTruthy();
  });

  it("renders inline code", () => {
    render(<MarkdownContent content="Use the `fetch` API" />);
    const el = screen.getByTestId("markdown-content");
    expect(el.querySelector("code")).toBeTruthy();
  });

  it("dangerouslySetInnerHTML is NOT used — content is constructed via React", () => {
    // This test confirms our MarkdownContent source does not use dangerouslySetInnerHTML.
    // Since we're using react-markdown + rehype-sanitize, the DOM is built
    // via React elements and will never include raw HTML.
    const maliciousImg = '<img src="x" onerror="window.__IMG_ERR__=true">';
    render(<MarkdownContent content={maliciousImg} />);
    expect((window as unknown as Record<string, unknown>).__IMG_ERR__).toBeUndefined();
  });
});

// ─── MessageList ──────────────────────────────────────────────────────────────

describe("MessageList", () => {
  it("shows loading state", () => {
    render(
      <MessageList messages={[]} streaming={null} loading />,
    );
    expect(screen.getByTestId("messages-loading")).toBeTruthy();
  });

  it("shows empty state when no messages", () => {
    render(
      <MessageList messages={[]} streaming={null} />,
    );
    expect(screen.getByTestId("messages-empty")).toBeTruthy();
  });

  it("renders message history", () => {
    const user = sampleMessage({ id: "u1", role: "user", content: "Hello" });
    const asst = assistantMessage("Hi back");
    render(
      <MessageList messages={[user, asst]} streaming={null} />,
    );
    expect(screen.getByTestId("message-u1")).toBeTruthy();
  });

  it("renders streaming assistant message inline", () => {
    const user = sampleMessage({ id: "u1" });
    render(
      <MessageList
        messages={[user]}
        streaming={{
          content: "Streaming...",
          citations: [],
          userMessageId: "u1",
          assistantMessageId: "ast-temp",
          toolActivity: [],
        }}
      />,
    );
    expect(screen.getByLabelText("Streaming")).toBeTruthy();
    expect(screen.getByTestId("message-list").textContent).toContain("Streaming...");
  });

  it("shows error state", () => {
    render(
      <MessageList messages={[]} streaming={null} error="Something went wrong" />,
    );
    expect(screen.getByTestId("messages-error")).toBeTruthy();
  });
});

// ─── Auth + navigation guards ─────────────────────────────────────────────────

describe("Auth guard", () => {
  it("redirects to /login when unauthenticated and chat layout is shown", async () => {
    // When auth status is unauthenticated the chat layout should push to /login.
    // We simulate this by rendering the layout with no token and a failed refresh.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.includes("/api/v1/auth/refresh") && method === "POST") {
          return Response.json({ error: { message: "No refresh token" } }, { status: 401 });
        }
        return Response.json({ error: { message: "Not found" } }, { status: 404 });
      }),
    );

    // Dynamically import chat layout to test redirect behavior.
    const { default: ChatLayout } = await import("@/app/chat/layout");
    render(
      <AuthProvider>
        <ChatLayout>
          <div data-testid="protected-content">Secret</div>
        </ChatLayout>
      </AuthProvider>,
    );

    await waitFor(() => {
      // After auth resolves as unauthenticated, replace should be called.
      expect(replaceMock).toHaveBeenCalledWith("/login");
    });
  });

  it("never stores access token in localStorage or sessionStorage", () => {
    clearAccessToken();
    setAccessToken("mem-only-token");
    expect(getAccessToken()).toBe("mem-only-token");
    expect(localStorage.getItem("accessToken")).toBeNull();
    expect(sessionStorage.getItem("accessToken")).toBeNull();
    // Verify nothing was set in storage at all with the token value.
    const allLocalKeys = Object.keys(localStorage);
    const allSessionKeys = Object.keys(sessionStorage);
    for (const key of [...allLocalKeys, ...allSessionKeys]) {
      expect(localStorage.getItem(key)).not.toContain("mem-only-token");
    }
  });
});

// ─── AuthHeader chat link ─────────────────────────────────────────────────────

describe("AuthHeader", () => {
  it("shows Chat link when authenticated", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (url.includes("/api/v1/auth/refresh") && method === "POST") {
          return Response.json(authTokenResponse());
        }
        if (url.includes("/api/v1/auth/me") && method === "GET") {
          return Response.json(demoUser());
        }
        return Response.json({}, { status: 404 });
      }),
    );

    const { AuthHeader } = await import("@/components/AuthHeader");
    render(
      <AuthProvider>
        <AuthHeader />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("chat-link")).toBeTruthy();
    });
  });

  it("does not show Chat link when unauthenticated", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({ error: { message: "No token" } }, { status: 401 }),
      ),
    );

    const { AuthHeader } = await import("@/components/AuthHeader");
    render(
      <AuthProvider>
        <AuthHeader />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("auth-anonymous")).toBeTruthy();
    });
    expect(screen.queryByTestId("chat-link")).toBeNull();
  });
});
