"""Shared citation mapping for live SSE and persisted conversation APIs.

Live streams historically emitted ``RagCitation`` (``citation_id``, no
``citation_index`` / ``id``). The chat UI expects ``MessageCitationResponse``
fields (``citation_index``, ``id``, …). Both paths must use this mapper so
reload and live rendering stay identical.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
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


def _normalized_terms(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _near_duplicate(left: str, right: str, *, threshold: float = 0.88) -> bool:
    """Return True for highly overlapping passages without expensive embeddings."""
    left_terms = _normalized_terms(left)
    right_terms = _normalized_terms(right)
    if not left_terms or not right_terms:
        return False
    left_counts = Counter(left_terms)
    right_counts = Counter(right_terms)
    overlap = sum((left_counts & right_counts).values())
    denominator = min(sum(left_counts.values()), sum(right_counts.values()))
    return denominator > 0 and (overlap / denominator) >= threshold


def dedupe_retrieved_chunks(retrieved: list[Any]) -> list[Any]:
    """Stable-order dedupe by identity and near-identical passage content."""
    seen_ids: set[uuid.UUID] = set()
    accepted_texts: list[str] = []
    unique: list[Any] = []
    for item in retrieved:
        chunk = getattr(item, "chunk", None)
        chunk_id = getattr(chunk, "id", None)
        if chunk_id is not None:
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)
        content = str(getattr(chunk, "content", "") or "").strip()
        if content and any(_near_duplicate(content, prior) for prior in accepted_texts):
            continue
        unique.append(item)
        if content:
            accepted_texts.append(content)
    return unique


def select_context_chunks(retrieved: list[Any], *, max_chars: int) -> list[Any]:
    """Select complete passages that fit the context budget in ranked order.

    The final passage is never silently truncated. This keeps citation excerpts and
    the actual model context aligned and avoids citations to text the model did not see.
    """
    selected: list[Any] = []
    used = 0
    for item in dedupe_retrieved_chunks(retrieved):
        content = str(getattr(getattr(item, "chunk", None), "content", "") or "").strip()
        if not content:
            continue
        index = len(selected) + 1
        block_chars = len(f"[{index}]\n{content}")
        separator = 2 if selected else 0
        if used + separator + block_chars > max_chars:
            continue
        selected.append(item)
        used += separator + block_chars
    return selected


def normalize_grounded_answer(text: str, *, citation_count: int | None = None) -> str:
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
    if citation_count is not None:

        def _valid_marker(match: re.Match[str]) -> str:
            index = int(match.group(1))
            return match.group(0) if 1 <= index <= citation_count else ""

        cleaned = re.sub(r"\[(\d+)\]", _valid_marker, cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r" +([.,;:!?])", r"\1", cleaned)
    return cleaned.strip()
