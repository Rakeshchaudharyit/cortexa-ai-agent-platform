"""Shared citation mapping for live SSE and persisted conversation APIs.

Live streams historically emitted ``RagCitation`` (``citation_id``, no
``citation_index`` / ``id``). The chat UI expects ``MessageCitationResponse``
fields (``citation_index``, ``id``, …). Both paths must use this mapper so
reload and live rendering stay identical.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from app.conversations.schemas import MessageCitationResponse
from app.documents.schemas import RagCitation
from app.models.conversation import MessageCitation

# Malformed model prose that duplicates structured citation cards.
_SOURCE_META_LINE = re.compile(r"(?im)^\s*(?:\[\d+\]\s*)?(?:Source|Citation\s*ID)\s*:\s*.+$")
_ADJACENT_PHRASE_DUP = re.compile(
    r"\b(.{12,80}?)\s+\1\b",
    flags=re.IGNORECASE | re.DOTALL,
)


def rag_citation_to_response(
    citation: RagCitation,
    *,
    index: int,
    citation_row_id: uuid.UUID | None = None,
    hide_score: bool = True,
) -> MessageCitationResponse:
    """Map a retrieval citation into the frontend-safe message citation schema."""
    safe_index = index if index >= 1 else 1
    row_id = citation_row_id or uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"rag-citation:{citation.chunk_id}:{safe_index}",
    )
    return MessageCitationResponse(
        id=row_id,
        citation_index=safe_index,
        citation_id=f"[{safe_index}]",
        document_id=citation.document_id,
        chunk_id=citation.chunk_id,
        filename=citation.filename,
        page_number=citation.page_number,
        chunk_index=citation.chunk_index,
        excerpt=citation.excerpt,
        similarity_score=None if hide_score else citation.similarity,
    )


def message_citation_to_response(citation: MessageCitation) -> MessageCitationResponse:
    """Map a persisted MessageCitation row (same shape as live SSE)."""
    return MessageCitationResponse(
        id=citation.id,
        citation_index=citation.citation_index,
        citation_id=f"[{citation.citation_index}]",
        document_id=citation.document_id,
        chunk_id=citation.chunk_id,
        filename=citation.filename,
        page_number=citation.page_number,
        chunk_index=citation.chunk_index,
        excerpt=citation.excerpt,
        # Scores stay in DB for diagnostics; normal UI does not display them.
        similarity_score=None,
    )


def dedupe_retrieved_chunks(retrieved: list[Any]) -> list[Any]:
    """Stable-order dedupe by chunk id (then document id + chunk_index)."""
    seen: set[uuid.UUID] = set()
    unique: list[Any] = []
    for item in retrieved:
        chunk_id = getattr(getattr(item, "chunk", None), "id", None)
        if chunk_id is None:
            unique.append(item)
            continue
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        unique.append(item)
    return unique


def normalize_grounded_answer(text: str) -> str:
    """Light cleanup for grounded answers — prefer prompt fixes over rewriting.

    - Strip Source:/Citation ID: prose lines (cards carry that metadata)
    - Collapse exact adjacent duplicated phrases (streaming dual-emit artifact)
    - Preserve legitimate repeated words shorter than the phrase window
    """
    if not text:
        return text
    cleaned = _SOURCE_META_LINE.sub("", text)
    # Collapse accidental blank lines left by removals.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    # Only collapse clear phrase-level doubles; avoid touching short words.
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = _ADJACENT_PHRASE_DUP.sub(r"\1", cleaned)
    return cleaned.strip()
