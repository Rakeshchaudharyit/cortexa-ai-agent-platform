"""Deterministic chunking tests."""

from __future__ import annotations

import pytest
from app.documents.chunking import ChunkingConfig, ChunkingService
from app.documents.exceptions import DocumentProcessingError, EmptyDocumentError
from app.documents.schemas import ExtractedSegment, ExtractionResult


def _service(
    *,
    chunk_size: int = 80,
    overlap: int = 20,
    min_characters: int = 10,
    max_chunks: int = 50,
) -> ChunkingService:
    return ChunkingService(
        ChunkingConfig(
            chunk_size=chunk_size,
            overlap=overlap,
            min_characters=min_characters,
            max_chunks=max_chunks,
        )
    )


def test_chunking_is_deterministic() -> None:
    text = (
        "Paragraph one explains Cortexa.\n\n"
        "Paragraph two covers document ingestion and embeddings.\n\n"
        "Paragraph three describes grounded retrieval answers."
    )
    extraction = ExtractionResult(
        text=text,
        character_count=len(text),
        media_type="text/plain",
        segments=[
            ExtractedSegment(text=part, paragraph_index=index)
            for index, part in enumerate(text.split("\n\n"))
        ],
    )
    service = _service(chunk_size=60, overlap=15, min_characters=10)
    first = service.chunk(extraction, document_id="doc-1", source_filename="a.txt")
    second = service.chunk(extraction, document_id="doc-1", source_filename="a.txt")
    assert [chunk.content for chunk in first] == [chunk.content for chunk in second]
    assert [chunk.index for chunk in first] == list(range(len(first)))
    assert all(chunk.metadata["document_id"] == "doc-1" for chunk in first)


def test_chunking_respects_overlap_and_size() -> None:
    paragraph = "A" * 200
    extraction = ExtractionResult(
        text=paragraph,
        character_count=len(paragraph),
        media_type="text/plain",
        segments=[ExtractedSegment(text=paragraph, paragraph_index=0)],
    )
    service = _service(chunk_size=50, overlap=10, min_characters=5)
    chunks = service.chunk(extraction, document_id="doc-2", source_filename="b.txt")
    assert len(chunks) >= 2
    assert all(chunk.character_count >= 5 for chunk in chunks)


def test_chunking_rejects_empty() -> None:
    extraction = ExtractionResult(
        text="   ",
        character_count=0,
        media_type="text/plain",
        segments=[],
    )
    with pytest.raises(EmptyDocumentError):
        _service().chunk(extraction, document_id="doc-3", source_filename="c.txt")


def test_chunking_rejects_too_many_chunks() -> None:
    parts = [f"Sentence number {index} with enough characters." for index in range(20)]
    text = "\n\n".join(parts)
    extraction = ExtractionResult(
        text=text,
        character_count=len(text),
        media_type="text/plain",
        segments=[
            ExtractedSegment(text=part, paragraph_index=index) for index, part in enumerate(parts)
        ],
    )
    service = _service(chunk_size=40, overlap=5, min_characters=10, max_chunks=3)
    with pytest.raises(DocumentProcessingError, match="maximum"):
        service.chunk(extraction, document_id="doc-4", source_filename="d.txt")


def test_chunking_config_rejects_bad_overlap() -> None:
    with pytest.raises(ValueError):
        ChunkingService(ChunkingConfig(chunk_size=10, overlap=10, min_characters=1, max_chunks=5))
