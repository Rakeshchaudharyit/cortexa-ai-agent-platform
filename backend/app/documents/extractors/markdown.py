"""Markdown extractor."""

from __future__ import annotations

from app.documents.exceptions import DocumentExtractionError, EmptyDocumentError
from app.documents.extractors.base import normalize_extracted_text
from app.documents.schemas import ExtractedSegment, ExtractionResult


class MarkdownExtractor:
    media_types = frozenset({"text/markdown", "text/x-markdown"})

    def extract(self, data: bytes, *, media_type: str, filename: str) -> ExtractionResult:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError("Markdown document is not valid UTF-8") from exc
        normalized = normalize_extracted_text(text)
        if not normalized:
            raise EmptyDocumentError()
        segments: list[ExtractedSegment] = []
        paragraphs = (part for part in normalized.split("\n\n") if part.strip())
        for index, paragraph in enumerate(paragraphs):
            segments.append(
                ExtractedSegment(
                    text=paragraph.strip(),
                    section="markdown",
                    paragraph_index=index,
                )
            )
        return ExtractionResult(
            text=normalized,
            character_count=len(normalized),
            media_type=media_type,
            segments=segments or [ExtractedSegment(text=normalized, paragraph_index=0)],
            metadata={"filename": filename, "encoding": "utf-8"},
        )
