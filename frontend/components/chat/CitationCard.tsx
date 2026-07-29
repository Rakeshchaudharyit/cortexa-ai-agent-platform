"use client";

import type { MessageCitation } from "@/types/api";

type Props = {
  citation: MessageCitation;
};

export function CitationCard({ citation }: Props) {
  const pageLabel = citation.page_number != null ? ` · p.${citation.page_number}` : "";
  const indexLabel = `[${citation.citation_index}]`;

  return (
    <div
      className="mt-1 rounded-lg border border-white/10 bg-slate-900/60 px-3 py-2 text-xs"
      data-testid={`citation-card-${citation.citation_index}`}
      aria-label={`Citation ${citation.citation_index}: ${citation.filename}${pageLabel}`}
    >
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-cyan-400 shrink-0">{indexLabel}</span>
        <span className="truncate font-medium text-slate-200">{citation.filename}{pageLabel}</span>
      </div>
      {citation.excerpt ? (
        <p className="mt-1 line-clamp-3 text-slate-400 leading-snug">
          &ldquo;{citation.excerpt}&rdquo;
        </p>
      ) : null}
    </div>
  );
}
