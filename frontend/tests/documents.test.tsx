import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentPanel } from "@/components/documents/DocumentPanel";
import { AuthProvider } from "@/components/AuthProvider";
import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth-token";
import { authenticatedUpload } from "@/services/auth";
import type { DocumentResponse, RagQueryResponse } from "@/types/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn(),
  }),
  usePathname: () => "/",
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

function sampleDocument(overrides: Partial<DocumentResponse> = {}): DocumentResponse {
  return {
    id: "22222222-2222-2222-2222-222222222222",
    original_filename: "notes.txt",
    media_type: "text/plain",
    file_size_bytes: 42,
    status: "ready",
    chunk_count: 1,
    character_count: 42,
    created_at: "2026-07-28T00:00:00Z",
    updated_at: "2026-07-28T00:00:00Z",
    processed_at: "2026-07-28T00:00:01Z",
    error_code: null,
    error_message: null,
    title: "notes.txt",
    folder_id: null,
    folder_name: null,
    tags: [],
    version_number: 1,
    knowledge_document_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    lifecycle_state: "active",
    is_active_version: true,
    supersedes_document_id: null,
    archived_at: null,
    is_archived: false,
    processing_mode: "synchronous",
    ...overrides,
  };
}

function sampleRagResponse(overrides: Partial<RagQueryResponse> = {}): RagQueryResponse {
  return {
    answer: "Cortexa is a local-first agent platform [1].",
    citations: [
      {
        citation_id: "[1]",
        document_id: "22222222-2222-2222-2222-222222222222",
        filename: "notes.txt",
        chunk_id: "33333333-3333-3333-3333-333333333333",
        chunk_index: 0,
        page_number: null,
        excerpt: "Cortexa is a local-first agent platform.",
        similarity: 0.91,
      },
    ],
    retrieval_count: 1,
    model: "qwen2.5:7b",
    provider: "fake",
    grounded: true,
    latency_ms: 12.5,
    ...overrides,
  };
}

type DocHandlers = {
  refresh?: () => Response;
  me?: () => Response;
  list?: () => Response;
  upload?: () => Response;
  delete?: () => Response;
  rag?: () => Response;
};

function stubDocumentApi(handlers: DocHandlers = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();

    if (url.includes("/api/v1/auth/refresh") && method === "POST") {
      return handlers.refresh?.() ?? Response.json(authTokenResponse());
    }
    if (url.includes("/api/v1/auth/me") && method === "GET") {
      return handlers.me?.() ?? Response.json(demoUser());
    }
    if (url.includes("/api/v1/documents/folders") && method === "GET") {
      return Response.json({ items: [], total: 0 });
    }
    if (url.includes("/api/v1/documents") && method === "GET" && !url.match(/documents\/[^/?]+$/)) {
      return (
        handlers.list?.() ??
        Response.json({
          items: [sampleDocument()],
          total: 1,
          limit: 20,
          offset: 0,
        })
      );
    }
    if (url.includes("/api/v1/documents") && method === "POST") {
      return handlers.upload?.() ?? Response.json(sampleDocument(), { status: 201 });
    }
    if (url.match(/\/api\/v1\/documents\/[^/?]+$/) && method === "DELETE") {
      return handlers.delete?.() ?? new Response(null, { status: 204 });
    }
    if (url.includes("/api/v1/rag/query") && method === "POST") {
      return handlers.rag?.() ?? Response.json(sampleRagResponse());
    }
    return Response.json(
      {
        error: { code: "not_found", message: "Resource not found", details: [] },
        request_id: "t",
      },
      { status: 404 },
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function renderAuthenticatedPanel(handlers: DocHandlers = {}) {
  setAccessToken("access-token-memory-only");
  const fetchMock = stubDocumentApi(handlers);
  render(
    <AuthProvider>
      <DocumentPanel />
    </AuthProvider>,
  );
  await waitFor(() => {
    expect(screen.getByTestId("document-panel")).toBeTruthy();
  });
  return fetchMock;
}

describe("DocumentPanel", () => {
  it("does not render when unauthenticated", async () => {
    stubDocumentApi({
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
        <DocumentPanel />
      </AuthProvider>,
    );
    await waitFor(() => {
      expect(screen.queryByTestId("document-panel")).toBeNull();
    });
  });

  it("exposes accessible labels for upload and question inputs", async () => {
    await renderAuthenticatedPanel();
    expect(screen.getByLabelText("Upload document")).toBeTruthy();
    expect(screen.getByLabelText("Ask a grounded question")).toBeTruthy();
  });

  it("rejects unsupported file extensions client-side", async () => {
    await renderAuthenticatedPanel();
    const file = new File(["hello"], "notes.exe", { type: "application/octet-stream" });
    const input = screen.getByTestId("document-upload-input");
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByTestId("document-upload-button"));
    await waitFor(() => {
      expect(screen.getByTestId("document-error")).toHaveTextContent("Unsupported file type");
    });
  });

  it("uploads a document successfully and refreshes the list", async () => {
    let listed = false;
    const fetchMock = await renderAuthenticatedPanel({
      list: () => {
        if (!listed) {
          listed = true;
          return Response.json({ items: [], total: 0, limit: 20, offset: 0 });
        }
        return Response.json({
          items: [sampleDocument({ original_filename: "readme.md" })],
          total: 1,
          limit: 20,
          offset: 0,
        });
      },
      upload: () =>
        Response.json(sampleDocument({ original_filename: "readme.md" }), { status: 201 }),
    });

    await waitFor(() => {
      expect(screen.getByTestId("document-list")).toHaveTextContent("No documents uploaded yet");
    });

    const file = new File(["# Hello"], "readme.md", { type: "text/markdown" });
    fireEvent.change(screen.getByTestId("document-upload-input"), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByTestId("document-upload-button"));

    await waitFor(() => {
      expect(screen.getByTestId("document-row")).toHaveTextContent("readme.md");
    });
    expect(fetchMock).toHaveBeenCalled();
    const uploadCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).includes("/api/v1/documents") &&
        (init?.method ?? "GET").toUpperCase() === "POST",
    );
    expect(uploadCall).toBeTruthy();
    expect(uploadCall?.[1]?.body).toBeInstanceOf(FormData);
    expect((uploadCall?.[1]?.headers as Record<string, string>)?.["Content-Type"]).toBeUndefined();
  });

  it("shows upload failure errors", async () => {
    await renderAuthenticatedPanel({
      list: () => Response.json({ items: [], total: 0, limit: 20, offset: 0 }),
      upload: () =>
        Response.json(
          {
            error: {
              code: "duplicate_document",
              message: "This document was already uploaded",
              details: [],
            },
            request_id: "t",
          },
          { status: 409 },
        ),
    });

    const file = new File(["text"], "dup.txt", { type: "text/plain" });
    fireEvent.change(screen.getByTestId("document-upload-input"), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByTestId("document-upload-button"));

    await waitFor(() => {
      expect(screen.getByTestId("document-error")).toHaveTextContent(
        "This document was already uploaded",
      );
    });
  });

  it("renders document status and metadata", async () => {
    await renderAuthenticatedPanel({
      list: () =>
        Response.json({
          items: [
            sampleDocument({ status: "ready", chunk_count: 3, file_size_bytes: 2048 }),
            sampleDocument({
              id: "44444444-4444-4444-4444-444444444444",
              original_filename: "bad.pdf",
              status: "failed",
              chunk_count: 0,
              error_message: "PDF contains no extractable text",
            }),
          ],
          total: 2,
          limit: 20,
          offset: 0,
        }),
    });

    await waitFor(() => {
      expect(screen.getAllByTestId("document-row")).toHaveLength(2);
    });
    expect(screen.getByText("Ready")).toBeTruthy();
    expect(screen.getByText("Failed")).toBeTruthy();
    expect(screen.getByText(/3 chunks/)).toBeTruthy();
    expect(screen.getByText(/PDF contains no extractable text/)).toBeTruthy();
  });

  it("deletes a document after confirmation", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    let deleted = false;
    await renderAuthenticatedPanel({
      list: () => {
        if (deleted) {
          return Response.json({ items: [], total: 0, limit: 20, offset: 0 });
        }
        return Response.json({
          items: [sampleDocument()],
          total: 1,
          limit: 20,
          offset: 0,
        });
      },
      delete: () => {
        deleted = true;
        return new Response(null, { status: 204 });
      },
    });

    await waitFor(() => {
      expect(screen.getByTestId("document-row")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("document-delete-button"));
    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.getByTestId("document-list")).toHaveTextContent("No documents uploaded yet");
    });
  });

  it("cancels delete when confirmation is declined", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    await renderAuthenticatedPanel();
    await waitFor(() => {
      expect(screen.getByTestId("document-row")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("document-delete-button"));
    expect(screen.getByTestId("document-row")).toBeTruthy();
  });

  it("disables RAG until a ready document exists", async () => {
    await renderAuthenticatedPanel({
      list: () => Response.json({ items: [], total: 0, limit: 20, offset: 0 }),
    });
    await waitFor(() => {
      expect(screen.getByTestId("rag-submit-button")).toBeDisabled();
    });
    expect(screen.getByTestId("rag-question-input")).toBeDisabled();
  });

  it("submits a RAG question and shows answer with citations", async () => {
    await renderAuthenticatedPanel();
    await waitFor(() => {
      expect(screen.getByTestId("rag-question-input")).not.toBeDisabled();
    });

    fireEvent.change(screen.getByTestId("rag-question-input"), {
      target: { value: "What is Cortexa?" },
    });
    expect(screen.getByTestId("rag-submit-button")).not.toBeDisabled();
    fireEvent.click(screen.getByTestId("rag-submit-button"));

    await waitFor(() => {
      expect(screen.getByTestId("rag-answer")).toHaveTextContent("local-first agent platform");
    });
    expect(screen.getByTestId("rag-citations")).toBeTruthy();
    expect(screen.getByTestId("rag-citation")).toHaveTextContent("notes.txt");
  });

  it("shows no-result display when retrieval is empty", async () => {
    await renderAuthenticatedPanel({
      rag: () =>
        Response.json(
          sampleRagResponse({
            answer:
              "I couldn’t find that information in the selected documents. Try choosing different documents or switch to General Agent mode.",
            citations: [],
            retrieval_count: 0,
            grounded: false,
          }),
        ),
    });

    fireEvent.change(screen.getByTestId("rag-question-input"), {
      target: { value: "Unrelated question" },
    });
    fireEvent.click(screen.getByTestId("rag-submit-button"));

    await waitFor(() => {
      expect(screen.getByTestId("rag-no-result")).toHaveTextContent(
        "couldn’t find that information",
      );
    });
    expect(screen.queryByTestId("rag-answer")).toBeNull();
  });

  it("refreshes once on 401 during upload and retries", async () => {
    setAccessToken("expired-token");
    let uploadAttempts = 0;
    const fetchMock = stubDocumentApi({
      list: () => Response.json({ items: [], total: 0, limit: 20, offset: 0 }),
      refresh: () => Response.json(authTokenResponse("refreshed-token")),
      upload: () => {
        uploadAttempts += 1;
        if (uploadAttempts === 1) {
          return Response.json(
            {
              error: { code: "unauthorized", message: "Unauthorized", details: [] },
              request_id: "t",
            },
            { status: 401 },
          );
        }
        return Response.json(sampleDocument(), { status: 201 });
      },
    });

    // Exercise the helper directly (same refresh-once path DocumentPanel uses).
    const formData = new FormData();
    formData.append("file", new File(["hi"], "a.txt", { type: "text/plain" }));
    const result = await authenticatedUpload("/api/v1/documents", formData);
    expect(result.ok).toBe(true);
    expect(getAccessToken()).toBe("refreshed-token");
    expect(uploadAttempts).toBe(2);
    const refreshCalls = fetchMock.mock.calls.filter(([url, init]) =>
      String(url).includes("/api/v1/auth/refresh") &&
      (init?.method ?? "GET").toUpperCase() === "POST",
    );
    expect(refreshCalls).toHaveLength(1);
  });

  it("does not store token or document content in localStorage", async () => {
    localStorage.clear();
    await renderAuthenticatedPanel();
    await waitFor(() => {
      expect(screen.getByTestId("document-panel")).toBeTruthy();
    });
    expect(localStorage.length).toBe(0);
    expect(getAccessToken()).toBe("access-token-memory-only");
  });
});
