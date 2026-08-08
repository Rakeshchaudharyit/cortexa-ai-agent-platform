import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/services/admin", () => ({
  createEvaluationCase: vi.fn(),
  deleteEvaluationCase: vi.fn(),
  fetchAdminUsers: vi.fn(),
  fetchEvaluationCases: vi.fn(),
  fetchEvaluationRuns: vi.fn(),
  runRagEvaluation: vi.fn(),
}));

import RagEvaluationsPage from "@/app/admin/evaluations/page";
import {
  createEvaluationCase,
  deleteEvaluationCase,
  fetchAdminUsers,
  fetchEvaluationCases,
  fetchEvaluationRuns,
} from "@/services/admin";

const ownerWithDocuments = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "owner@example.com",
  full_name: "Knowledge Owner",
  role: "user",
  status: "active",
  is_email_verified: true,
  created_at: "2026-08-04T00:00:00Z",
  last_login_at: null,
  conversations_count: 1,
  documents_count: 3,
  memories_count: 0,
};

const ownerWithoutDocuments = {
  ...ownerWithDocuments,
  id: "22222222-2222-2222-2222-222222222222",
  email: "empty@example.com",
  full_name: "Empty Owner",
  documents_count: 0,
};

describe("RAG evaluation owner selector", () => {
  beforeEach(() => {
    vi.mocked(fetchEvaluationCases).mockResolvedValue({
      ok: true,
      status: 200,
      data: { items: [], total: 0 },
    } as never);
    vi.mocked(fetchEvaluationRuns).mockResolvedValue({
      ok: true,
      status: 200,
      data: { items: [], total: 0 },
    } as never);
    vi.mocked(fetchAdminUsers).mockResolvedValue({
      ok: true,
      status: 200,
      data: { items: [ownerWithoutDocuments, ownerWithDocuments], total: 2, limit: 100, offset: 0 },
    } as never);
    vi.mocked(createEvaluationCase).mockResolvedValue({
      ok: true,
      status: 201,
      data: {
        id: "case-1",
        owner_user_id: ownerWithDocuments.id,
        name: "Architecture test",
        question: "Which architecture components are documented?",
        expected_answer: null,
        expected_keywords: [],
        expected_document_ids: [],
        should_answer: true,
        enabled: true,
        created_at: "2026-08-04T00:00:00Z",
        updated_at: "2026-08-04T00:00:00Z",
      },
    } as never);
  });

  it("selects a user with documents and submits its UUID internally", async () => {
    const user = userEvent.setup();
    render(<RagEvaluationsPage />);

    await waitFor(() =>
      expect(screen.getByTestId("evaluation-owner-select")).toHaveValue(
        ownerWithDocuments.id,
      ),
    );
    expect(screen.getByTestId("evaluation-owner-summary")).toHaveTextContent(
      "3 documents",
    );

    await user.type(screen.getByPlaceholderText("Case name"), "Architecture test");
    await user.type(
      screen.getByPlaceholderText("Question"),
      "Which architecture components are documented?",
    );
    await user.click(screen.getByTestId("evaluation-save-case"));

    await waitFor(() =>
      expect(createEvaluationCase).toHaveBeenCalledWith(
        expect.objectContaining({ owner_user_id: ownerWithDocuments.id }),
      ),
    );
  });

  it("filters owners by name or email without exposing a UUID input", async () => {
    const user = userEvent.setup();
    render(<RagEvaluationsPage />);
    await waitFor(() => expect(fetchAdminUsers).toHaveBeenCalled());

    expect(screen.queryByPlaceholderText("Owner user UUID")).not.toBeInTheDocument();
    await user.type(screen.getByTestId("evaluation-owner-search"), "empty@");
    const select = screen.getByTestId("evaluation-owner-select");
    expect(select).toHaveTextContent("Empty Owner");
  });
  it("shows success and renders the new case immediately after creation", async () => {
    const user = userEvent.setup();
    render(<RagEvaluationsPage />);

    await waitFor(() =>
      expect(screen.getByTestId("evaluation-owner-select")).toHaveValue(
        ownerWithDocuments.id,
      ),
    );

    await user.type(screen.getByPlaceholderText("Case name"), "Architecture test");
    await user.type(
      screen.getByPlaceholderText("Question"),
      "Which architecture components are documented?",
    );
    await user.click(screen.getByTestId("evaluation-save-case"));

    expect(
      await screen.findByTestId("evaluation-success-message"),
    ).toHaveTextContent("created successfully");
    expect(screen.getByText("Architecture test")).toBeInTheDocument();
    expect(screen.getByText("Which architecture components are documented?")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Case name")).toHaveValue("");
    expect(screen.getByPlaceholderText("Question")).toHaveValue("");
  });

  it("deletes a case immediately after confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchEvaluationCases).mockResolvedValueOnce({
      ok: true,
      status: 200,
      data: { items: [{
        id: "case-delete",
        owner_user_id: ownerWithDocuments.id,
        name: "Delete me",
        question: "Temporary evaluation case?",
        expected_answer: null,
        expected_keywords: [],
        expected_document_ids: [],
        should_answer: true,
        enabled: true,
        created_at: "2026-08-04T00:00:00Z",
        updated_at: "2026-08-04T00:00:00Z",
      }], total: 1 },
    } as never);
    vi.mocked(deleteEvaluationCase).mockResolvedValue({ ok: true, status: 204, data: null } as never);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<RagEvaluationsPage />);
    expect(await screen.findByText("Delete me")).toBeInTheDocument();
    await user.click(screen.getByTestId("evaluation-delete-case-delete"));

    await waitFor(() => expect(deleteEvaluationCase).toHaveBeenCalledWith("case-delete"));
    expect(screen.queryByText("Delete me")).not.toBeInTheDocument();
    expect(await screen.findByTestId("evaluation-success-message")).toHaveTextContent("deleted successfully");
  });

});
