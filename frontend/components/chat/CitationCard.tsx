"use client";

import type { MessageCitation } from "@/types/api";

type Props = {
  citation: MessageCitation;
};

/** Normalize live-stream or persisted citations into a stable display shape. */
export function normalizeCitation(raw: Partial<MessageCitation> & Record<string, unknown>): MessageCitation | null {
  const indexRaw =
    raw.citation_index ??
    (typeof raw.index === "number" ? raw.index : undefined) ??
    (typeof raw.citation_id === "string"
      ? Number(String(raw.citation_id).replace(/[^\d]/g, ""))
      : undefined);
  const citation_index = typeof indexRaw === "number" && Number.isFinite(indexRaw) && indexRaw >= 1
    ? indexRaw
    : null;
  const filename =
    (typeof raw.filename === "string" && raw.filename) ||
    (typeof raw.document_title === "string" && raw.document_title) ||
    "";
  if (citation_index == null || !filename) return null;

  return {
    id: typeof raw.id === "string" && raw.id ? raw.id : `citation-${citation_index}-${filename}`,
    citation_index,
    citation_id: typeof raw.citation_id === "string" ? raw.citation_id : `[${citation_index}]`,
    document_id: typeof raw.document_id === "string" ? raw.document_id : null,
    chunk_id: typeof raw.chunk_id === "string" ? raw.chunk_id : null,
    filename,
    page_number: typeof raw.page_number === "number" ? raw.page_number : null,
    chunk_index: typeof raw.chunk_index === "number" ? raw.chunk_index : 0,
    excerpt: typeof raw.excerpt === "string" ? raw.excerpt : "",
    similarity_score: null,
  };
}

export function CitationCard({ citation }: Props) {
  const normalized = normalizeCitation(citation);
  if (!normalized) return null;

  const pageLabel = normalized.page_number != null ? ` · p.${normalized.page_number}` : "";
  const indexLabel = `[${normalized.citation_index}]`;

  return (
    <div
      className="mt-1 w-full max-w-full rounded-lg border border-white/10 bg-slate-900/60 px-3 py-2 text-xs sm:max-w-md"
      data-testid={`citation-card-${normalized.citation_index}`}
      aria-label={`Citation ${normalized.citation_index}: ${normalized.filename}${pageLabel}`}
    >
      <div className="flex min-w-0 items-baseline gap-2">
        <span className="font-mono text-cyan-400 shrink-0">{indexLabel}</span>
        <span className="truncate font-medium text-slate-200">
          {normalized.filename}
          {pageLabel}
        </span>
      </div>
      {normalized.excerpt ? (
        <p className="mt-1 line-clamp-3 break-words text-slate-400 leading-snug">
          &ldquo;{normalized.excerpt}&rdquo;
        </p>
      ) : null}
    </div>
  );
}
