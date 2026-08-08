import {
  authenticatedDelete,
  authenticatedGet,
  authenticatedPatch,
  authenticatedPost,
  authenticatedUpload,
} from "@/services/auth";
import { apiGet } from "@/lib/api";
import type {
  ApiResult,
  DocumentFolderListResponse,
  DocumentFolderResponse,
  DocumentListResponse,
  DocumentMetadataUpdate,
  DocumentResponse,
  DocumentTimelineResponse,
  DocumentVersionCompareResponse,
  DocumentVersionHistoryResponse,
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

export async function listDocuments(options: { archived?: boolean; folderId?: string | null } = {}): Promise<
  | { ok: true; data: DocumentListResponse; status: number }
  | { ok: false; error: string; status: number | null }
> {
  const params = new URLSearchParams();
  if (options.archived) params.set("archived", "true");
  if (options.folderId) params.set("folder_id", options.folderId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return authenticatedGet<DocumentListResponse>(`/api/v1/documents${suffix}`);
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
  folderId?: string | null,
  supersedesDocumentId?: string | null,
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
  if (folderId) formData.append("folder_id", folderId);
  if (supersedesDocumentId) formData.append("supersedes_document_id", supersedesDocumentId);
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


export async function listDocumentFolders() {
  return authenticatedGet<DocumentFolderListResponse>("/api/v1/documents/folders");
}

export async function createDocumentFolder(name: string, description?: string) {
  return authenticatedPost<DocumentFolderResponse>(
    "/api/v1/documents/folders",
    { name, description: description || null },
    [201],
  );
}

export async function deleteDocumentFolder(id: string) {
  return authenticatedDelete(`/api/v1/documents/folders/${id}`);
}

export async function updateDocumentMetadata(id: string, body: DocumentMetadataUpdate) {
  return authenticatedPatch<DocumentResponse>(`/api/v1/documents/${id}`, body);
}

export async function archiveDocument(id: string) {
  return authenticatedPost<DocumentResponse>(`/api/v1/documents/${id}/archive`);
}

export async function restoreDocument(id: string) {
  return authenticatedPost<DocumentResponse>(`/api/v1/documents/${id}/restore`);
}


export async function getDocumentVersions(id: string) {
  return authenticatedGet<DocumentVersionHistoryResponse>(`/api/v1/documents/${id}/versions`);
}

export async function getDocumentTimeline(id: string) {
  return authenticatedGet<DocumentTimelineResponse>(`/api/v1/documents/${id}/timeline`);
}

export async function compareDocumentVersions(leftId: string, rightId: string) {
  return authenticatedGet<DocumentVersionCompareResponse>(
    `/api/v1/documents/${leftId}/compare/${rightId}`,
  );
}

export async function activateDocumentVersion(id: string) {
  return authenticatedPost<DocumentResponse>(`/api/v1/documents/${id}/activate`);
}


export async function reindexDocumentVersion(id: string) {
  return authenticatedPost<DocumentResponse>(`/api/v1/documents/${id}/reindex`);
}
