"""Text extraction protocol and helpers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.documents.schemas import ExtractionResult


@runtime_checkable
class DocumentExtractor(Protocol):
    media_types: frozenset[str]

    def extract(self, data: bytes, *, media_type: str, filename: str) -> ExtractionResult:
        """Extract normalized text from raw document bytes."""


def normalize_extracted_text(text: str) -> str:
    """Normalize line endings, strip null bytes, and collapse extreme whitespace runs."""
    cleaned = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in cleaned.split("\n")]
    # Preserve paragraph boundaries (blank lines) while trimming trailing spaces.
    return "\n".join(lines).strip()
