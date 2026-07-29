"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";
import {
  deleteDocument,
  listDocuments,
  queryRag,
  uploadDocument,
  validateDocumentFile,
} from "@/services/documents";
import type { DocumentResponse, RagCitation, RagQueryResponse } from "@/types/api";

type PanelState = "idle" | "loading" | "uploading" | "querying";

function statusLabel(status: DocumentResponse["status"]): string {
  switch (status) {
    case "ready":
      return "Ready";
    case "pending":
      return "Pending";
    case "processing":
      return "Processing";
    case "failed":
      return "Failed";
    default:
      return status;
  }
}

function statusTone(status: DocumentResponse["status"]): string {
  switch (status) {
    case "ready":
      return "text-emerald-300";
    case "failed":
      return "text-rose-300";
    case "processing":
    case "pending":
      return "text-amber-300";
    default:
      return "text-slate-300";
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KiB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
}

export function DocumentPanel() {
  const { status: authStatus } = useAuth();
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [panelState, setPanelState] = useState<PanelState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [ragResult, setRagResult] = useState<RagQueryResponse | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const readyCount = documents.filter((doc) => doc.status === "ready").length;
  const canQuery = readyCount > 0 && panelState !== "querying" && panelState !== "uploading";

  const refreshDocuments = useCallback(async () => {
    setPanelState("loading");
    setError(null);
    const result = await listDocuments();
    if (!result.ok) {
      setDocuments([]);
      setError(result.error);
      setPanelState("idle");
      return;
    }
    setDocuments(result.data.items);
    setPanelState("idle");
  }, []);

  useEffect(() => {
    if (authStatus !== "authenticated") {
      setDocuments([]);
      setRagResult(null);
      setError(null);
      return;
    }
    void refreshDocuments();
  }, [authStatus, refreshDocuments]);

  if (authStatus !== "authenticated") {
    return null;
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setRagResult(null);

    if (!selectedFile) {
      setError("Choose a document to upload");
      return;
    }

    const validationError = validateDocumentFile(selectedFile);
    if (validationError) {
      setError(validationError);
      return;
    }

    setPanelState("uploading");
    const result = await uploadDocument(selectedFile);
    if (!result.ok) {
      setError(result.error);
      setPanelState("idle");
      return;
    }

    setSelectedFile(null);
    const input = document.getElementById("document-upload-input") as HTMLInputElement | null;
    if (input) {
      input.value = "";
    }
    await refreshDocuments();
  }

  async function handleDelete(doc: DocumentResponse) {
    const confirmed = window.confirm(
      `Delete “${doc.original_filename}”? This cannot be undone.`,
    );
    if (!confirmed) {
      return;
    }
    setError(null);
    const result = await deleteDocument(doc.id);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setRagResult(null);
    await refreshDocuments();
  }

  async function handleRagSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setRagResult(null);

    const trimmed = question.trim();
    if (!trimmed) {
      setError("Enter a question about your documents");
      return;
    }
    if (readyCount === 0) {
      setError("Upload at least one ready document before asking a question");
      return;
    }

    setPanelState("querying");
    const result = await queryRag({ question: trimmed });
    if (!result.ok) {
      setError(result.error);
      setPanelState("idle");
      return;
    }
    setRagResult(result.data);
    setPanelState("idle");
  }

  return (
    <section
      id="documents"
      className="flex flex-col gap-6 rounded-2xl border border-white/10 bg-white/[0.03] p-6"
      data-testid="document-panel"
      aria-labelledby="documents-heading"
    >
      <div className="flex flex-col gap-2">
        <h2 id="documents-heading" className="text-xl font-semibold text-slate-50">
          Documents &amp; grounded Q&amp;A
        </h2>
        <p className="max-w-2xl text-sm leading-relaxed text-slate-400">
          Upload private documents (synchronous ingest), then ask questions answered only from
          your files with citations. Supported types: .txt, .md, .pdf, .docx — max 5 MiB.
        </p>
      </div>

      <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={handleUpload}>
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <label htmlFor="document-upload-input" className="text-sm font-medium text-slate-200">
            Upload document
          </label>
          <input
            id="document-upload-input"
            data-testid="document-upload-input"
            type="file"
            accept=".txt,.md,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            className="block w-full text-sm text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-cyan-500/20 file:px-3 file:py-2 file:text-sm file:font-medium file:text-cyan-100"
            disabled={panelState === "uploading"}
            onChange={(event) => {
              const file = event.target.files?.[0] ?? null;
              setSelectedFile(file);
              setError(null);
            }}
          />
        </div>
        <button
          type="submit"
          data-testid="document-upload-button"
          disabled={panelState === "uploading" || !selectedFile}
          className="rounded-lg bg-cyan-500/20 px-4 py-2 text-sm font-medium text-cyan-100 ring-1 ring-cyan-400/30 transition hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {panelState === "uploading" ? "Uploading…" : "Upload"}
        </button>
      </form>

      {error ? (
        <p
          className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-200 ring-1 ring-rose-400/20"
          data-testid="document-error"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            Your documents
          </h3>
          <button
            type="button"
            onClick={() => void refreshDocuments()}
            disabled={panelState === "loading" || panelState === "uploading"}
            className="rounded-lg bg-slate-500/20 px-3 py-1.5 text-xs font-medium text-slate-200 ring-1 ring-white/10 hover:bg-slate-500/30 disabled:opacity-50"
          >
            {panelState === "loading" ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {documents.length === 0 ? (
          <p className="text-sm text-slate-400" data-testid="document-list">
            No documents uploaded yet.
          </p>
        ) : (
          <ul className="flex flex-col gap-2" data-testid="document-list">
            {documents.map((doc) => (
              <li
                key={doc.id}
                className="flex flex-col gap-2 rounded-xl border border-white/10 bg-slate-950/40 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                data-testid="document-row"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-100">
                    {doc.original_filename}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">
                    <span className={statusTone(doc.status)}>{statusLabel(doc.status)}</span>
                    {" · "}
                    {formatBytes(doc.file_size_bytes)}
                    {" · "}
                    {doc.chunk_count} chunks
                    {doc.error_message ? ` · ${doc.error_message}` : ""}
                  </p>
                </div>
                <button
                  type="button"
                  data-testid="document-delete-button"
                  onClick={() => void handleDelete(doc)}
                  className="shrink-0 rounded-lg bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-200 ring-1 ring-rose-400/20 hover:bg-rose-500/20"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <form className="flex flex-col gap-3 border-t border-white/10 pt-6" onSubmit={handleRagSubmit}>
        <label htmlFor="rag-question-input" className="text-sm font-medium text-slate-200">
          Ask a grounded question
        </label>
        <textarea
          id="rag-question-input"
          data-testid="rag-question-input"
          rows={3}
          value={question}
          disabled={!canQuery}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={
            readyCount === 0
              ? "Upload a ready document before asking a question"
              : "Ask a question answered only from your uploaded documents"
          }
          className="w-full rounded-xl border border-white/10 bg-slate-950/50 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
        />
        <button
          type="submit"
          data-testid="rag-submit-button"
          disabled={!canQuery || !question.trim()}
          className="w-fit rounded-lg bg-cyan-500/20 px-4 py-2 text-sm font-medium text-cyan-100 ring-1 ring-cyan-400/30 transition hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {panelState === "querying" ? "Searching…" : "Ask"}
        </button>
      </form>

      {ragResult ? <RagResultView result={ragResult} /> : null}
    </section>
  );
}

function RagResultView({ result }: { result: RagQueryResponse }) {
  const hasCitations = result.citations.length > 0;
  const noResult = !result.grounded || result.retrieval_count === 0;

  return (
    <div className="flex flex-col gap-4 border-t border-white/10 pt-6">
      {noResult ? (
        <p
          className="rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-100 ring-1 ring-amber-400/20"
          data-testid="rag-no-result"
        >
          {result.answer}
        </p>
      ) : (
        <div
          className="rounded-xl border border-white/10 bg-slate-950/40 px-4 py-3"
          data-testid="rag-answer"
        >
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
            Answer
          </h3>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-100">
            {result.answer}
          </p>
        </div>
      )}

      {hasCitations ? (
        <div data-testid="rag-citations" className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Citations
          </h3>
          {result.citations.map((citation: RagCitation) => (
            <article
              key={`${citation.citation_id}-${citation.chunk_id}`}
              className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3"
              data-testid="rag-citation"
            >
              <p className="text-xs font-medium text-cyan-200">
                {citation.citation_id} {citation.filename}
                {citation.page_number != null ? ` · p.${citation.page_number}` : ""}
                {" · "}
                similarity {(citation.similarity * 100).toFixed(0)}%
              </p>
              <p className="mt-1 text-sm leading-relaxed text-slate-300">{citation.excerpt}</p>
            </article>
          ))}
        </div>
      ) : null}
    </div>
  );
}
