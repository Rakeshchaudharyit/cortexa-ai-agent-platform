import {
  authenticatedDelete,
  authenticatedGet,
  authenticatedPost,
  authenticatedUpload,
} from "@/services/auth";
import { apiGet } from "@/lib/api";
import type {
  ApiResult,
  DocumentListResponse,
  DocumentResponse,
  EmbeddingStatusResponse,
  RagQueryRequest,
  RagQueryResponse,
} from "@/types/api";

const ALLOWED_EXTENSIONS = new Set([".txt", ".md", ".pdf", ".docx"]);
const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024; // 5 MiB

export function getDocumentExtension(filename: string): string {
  const idx = filename.lastIndexOf(".");
  if (idx < 0) {
    return "";
  }
  return filename.slice(idx).toLowerCase();
}

export function validateDocumentFile(file: File): string | null {
  const extension = getDocumentExtension(file.name);
  if (!ALLOWED_EXTENSIONS.has(extension)) {
    return "Unsupported file type. Allowed: .txt, .md, .pdf, .docx";
  }
  if (file.size <= 0) {
    return "File is empty";
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return "File exceeds the 5 MiB size limit";
  }
  return null;
}

export async function listDocuments(): Promise<
  | { ok: true; data: DocumentListResponse; status: number }
  | { ok: false; error: string; status: number | null }
> {
  return authenticatedGet<DocumentListResponse>("/api/v1/documents");
}

export async function getDocument(
  id: string,
): Promise<
  | { ok: true; data: DocumentResponse; status: number }
  | { ok: false; error: string; status: number | null }
> {
  return authenticatedGet<DocumentResponse>(`/api/v1/documents/${id}`);
}

export async function uploadDocument(
  file: File,
): Promise<
  | { ok: true; data: DocumentResponse; status: number }
  | { ok: false; error: string; status: number | null }
> {
  const validationError = validateDocumentFile(file);
  if (validationError) {
    return { ok: false, error: validationError, status: null };
  }
  const formData = new FormData();
  formData.append("file", file);
  return authenticatedUpload<DocumentResponse>("/api/v1/documents", formData);
}

export async function deleteDocument(
  id: string,
): Promise<
  | { ok: true; data: null; status: number }
  | { ok: false; error: string; status: number | null }
> {
  return authenticatedDelete(`/api/v1/documents/${id}`);
}

export async function queryRag(
  body: RagQueryRequest,
): Promise<
  | { ok: true; data: RagQueryResponse; status: number }
  | { ok: false; error: string; status: number | null }
> {
  return authenticatedPost<RagQueryResponse>("/api/v1/rag/query", body);
}

export function getEmbeddingStatus(): Promise<ApiResult<EmbeddingStatusResponse>> {
  return apiGet<EmbeddingStatusResponse>("/api/v1/embeddings/status");
}
