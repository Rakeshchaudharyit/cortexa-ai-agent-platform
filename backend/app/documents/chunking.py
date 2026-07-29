"""Deterministic document chunking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.documents.exceptions import DocumentProcessingError, EmptyDocumentError
from app.documents.schemas import ExtractionResult, TextChunk


@dataclass(frozen=True)
class ChunkingConfig:
    chunk_size: int
    overlap: int
    min_characters: int
    max_chunks: int


class ChunkingService:
    """Paragraph-aware character chunker with stable ordering and overlap."""

    def __init__(self, config: ChunkingConfig) -> None:
        if config.overlap >= config.chunk_size:
            raise ValueError("chunk overlap must be smaller than chunk size")
        self._config = config

    def chunk(
        self,
        extraction: ExtractionResult,
        *,
        document_id: str,
        source_filename: str,
    ) -> list[TextChunk]:
        text = extraction.text.strip()
        if not text:
            raise EmptyDocumentError()

        paragraphs = self._paragraphs_with_metadata(extraction)
        raw_chunks: list[tuple[str, dict[str, Any]]] = []
        buffer = ""
        buffer_meta: dict[str, Any] = {}

        for paragraph, meta in paragraphs:
            if len(paragraph) > self._config.chunk_size:
                if buffer.strip():
                    raw_chunks.append((buffer.strip(), buffer_meta))
                    buffer = ""
                    buffer_meta = {}
                for piece in self._split_oversized(paragraph):
                    raw_chunks.append((piece, dict(meta)))
                continue

            candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
            if len(candidate) <= self._config.chunk_size:
                if not buffer:
                    buffer_meta = dict(meta)
                buffer = candidate
            else:
                if buffer.strip():
                    raw_chunks.append((buffer.strip(), buffer_meta))
                buffer = paragraph
                buffer_meta = dict(meta)

        if buffer.strip():
            raw_chunks.append((buffer.strip(), buffer_meta))

        # Apply overlap by carrying a suffix from the previous chunk.
        overlapped: list[tuple[str, dict[str, Any]]] = []
        previous = ""
        for content, meta in raw_chunks:
            if previous and self._config.overlap > 0:
                suffix = previous[-self._config.overlap :]
                merged = f"{suffix}\n{content}".strip()
                if len(merged) > self._config.chunk_size + self._config.overlap:
                    merged = content
                content = merged
            if len(content) < self._config.min_characters:
                continue
            overlapped.append((content, meta))
            previous = content

        if not overlapped:
            raise EmptyDocumentError("No usable chunks were produced from the document")

        if len(overlapped) > self._config.max_chunks:
            raise DocumentProcessingError(
                f"Document exceeds the maximum of {self._config.max_chunks} chunks"
            )

        chunks: list[TextChunk] = []
        cursor = 0
        for index, (content, meta) in enumerate(overlapped):
            start = text.find(content[: min(64, len(content))], cursor)
            if start < 0:
                start = cursor
            end = start + len(content)
            chunk_meta = {
                "document_id": document_id,
                "chunk_index": index,
                "source_filename": source_filename,
                "char_start": start,
                "char_end": end,
                **{k: v for k, v in meta.items() if v is not None},
            }
            chunks.append(
                TextChunk(
                    index=index,
                    content=content,
                    character_count=len(content),
                    metadata=chunk_meta,
                )
            )
            cursor = max(cursor, start + 1)

        return chunks

    def _paragraphs_with_metadata(
        self,
        extraction: ExtractionResult,
    ) -> list[tuple[str, dict[str, Any]]]:
        if extraction.segments:
            items: list[tuple[str, dict[str, Any]]] = []
            for segment in extraction.segments:
                text = segment.text.strip()
                if not text:
                    continue
                items.append(
                    (
                        text,
                        {
                            "page_number": segment.page_number,
                            "section": segment.section,
                            "paragraph_index": segment.paragraph_index,
                        },
                    )
                )
            if items:
                return items
        return [
            (part.strip(), {"paragraph_index": index})
            for index, part in enumerate(extraction.text.split("\n\n"))
            if part.strip()
        ]

    def _split_oversized(self, paragraph: str) -> list[str]:
        size = self._config.chunk_size
        overlap = self._config.overlap
        pieces: list[str] = []
        start = 0
        length = len(paragraph)
        while start < length:
            end = min(start + size, length)
            piece = paragraph[start:end].strip()
            if piece:
                pieces.append(piece)
            if end >= length:
                break
            start = max(end - overlap, start + 1)
        return pieces
