"""Retry-safe document ingestion and re-index execution for the queue worker."""
from __future__ import annotations

import hashlib
import logging
import math
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import lazyload
from sqlalchemy.exc import DBAPIError

from app.db.session import get_session_factory
from app.documents.exceptions import DocumentProcessingError
from app.models.document import (
    EMBEDDING_DIMENSION,
    Document,
    DocumentChunk,
    KnowledgeDocumentEvent,
)
from app.models.enums import DocumentStatus
from app.models.user import User
from app.services.documents import DocumentService

ProgressCallback = Callable[[int, str], Awaitable[bool]]

logger = logging.getLogger("cortexa.jobs.document_ingestion")


class DocumentFinalizationError(DocumentProcessingError):
    """Safe stage-aware error for durable document finalization."""

    def __init__(self, stage: str, message: str = "Document finalization failed") -> None:
        super().__init__(message)
        self.stage = stage
        self.code = f"document_finalization_{stage}_failed"


def _validate_embeddings(vectors: list[list[float]], *, expected_count: int) -> None:
    if len(vectors) != expected_count:
        raise DocumentProcessingError("Embedding batch length mismatch")
    for index, vector in enumerate(vectors):
        if len(vector) != EMBEDDING_DIMENSION:
            raise DocumentProcessingError(
                f"Embedding dimension mismatch for chunk {index}: "
                f"expected {EMBEDDING_DIMENSION}, received {len(vector)}"
            )
        if not all(math.isfinite(value) for value in vector):
            raise DocumentProcessingError(
                f"Embedding vector for chunk {index} contained non-finite values"
            )


def _safe_db_detail(exc: DBAPIError) -> str:
    original = getattr(exc, "orig", None)
    detail = str(original or exc).replace("\n", " ").strip()
    return detail[:500] if detail else type(exc).__name__


async def process_document_job(
    *,
    document_service: DocumentService,
    document_id: uuid.UUID,
    operation: str,
    progress: ProgressCallback,
) -> dict[str, object] | None:
    """Build a complete index outside the database, then swap chunks atomically."""
    factory = get_session_factory()
    async with factory() as session:
        document = await session.get(Document, document_id)
        if document is None:
            raise DocumentProcessingError("Document no longer exists")
        snapshot = {
            "storage_key": document.storage_key,
            "media_type": document.media_type,
            "original_filename": document.original_filename,
            "user_id": document.user_id,
            "version_number": document.version_number,
        }
        if operation == "ingest":
            document.status = DocumentStatus.processing
            document.lifecycle_state = "processing"
            event_type = "ingestion_started"
        else:
            event_type = "reindex_started"
        session.add(
            KnowledgeDocumentEvent(
                knowledge_document_id=document.knowledge_document_id,
                document_id=document.id,
                actor_user_id=document.user_id,
                event_type=event_type,
                event_metadata={"version_number": document.version_number, "background": True},
            )
        )
        await session.commit()

    if not await progress(10, "Extracting text"):
        return None
    data = await document_service.storage.get_bytes(key=str(snapshot["storage_key"]))
    extraction = document_service.extraction_service.extract(
        data=data,
        media_type=str(snapshot["media_type"]),
        filename=str(snapshot["original_filename"]),
    )

    if not await progress(30, "Creating chunks"):
        return None
    text_chunks = document_service.chunking_service.chunk(
        extraction,
        document_id=str(document_id),
        source_filename=str(snapshot["original_filename"]),
    )

    if not await progress(45, "Generating embeddings"):
        return None
    batch_size = document_service.settings.embedding_batch_size
    embeddings: list[list[float]] = []
    total = max(1, len(text_chunks))
    for start in range(0, len(text_chunks), batch_size):
        batch = text_chunks[start : start + batch_size]
        vectors = await document_service.embedding_provider.embed_batch(
            [chunk.content for chunk in batch]
        )
        if len(vectors) != len(batch):
            raise DocumentProcessingError("Embedding batch length mismatch")
        embeddings.extend(vectors)
        completed = min(len(text_chunks), start + len(batch))
        percent = 45 + int((completed / total) * 35)
        if not await progress(min(percent, 80), "Generating embeddings"):
            return None

    _validate_embeddings(embeddings, expected_count=len(text_chunks))

    if not await progress(90, "Finalizing index"):
        return None

    async with factory() as session:
        document = await session.scalar(
            select(Document)
            .options(lazyload(Document.folder))
            .where(Document.id == document_id)
            .with_for_update(of=Document)
        )
        if document is None:
            raise DocumentProcessingError("Document no longer exists")
        try:
            # Checkpoint 1: replace chunks and force vector/constraint validation now.
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
            )
            for chunk, vector in zip(text_chunks, embeddings, strict=True):
                session.add(
                    DocumentChunk(
                        document_id=document.id,
                        user_id=document.user_id,
                        chunk_index=chunk.index,
                        content=chunk.content,
                        content_sha256=hashlib.sha256(
                            chunk.content.encode("utf-8")
                        ).hexdigest(),
                        character_count=chunk.character_count,
                        embedding=vector,
                        chunk_metadata=dict(chunk.metadata),
                    )
                )
            await session.flush()
        except DBAPIError as exc:
            await session.rollback()
            logger.exception(
                "document_finalization_failed document_id=%s stage=chunks db_detail=%s",
                document_id,
                _safe_db_detail(exc),
            )
            raise DocumentFinalizationError("chunks") from exc

        try:
            # Checkpoint 2: persist ready-state metadata before version switching.
            document.status = DocumentStatus.ready
            document.chunk_count = len(text_chunks)
            document.character_count = extraction.character_count
            document.processed_at = datetime.now(UTC)
            document.error_code = None
            document.error_message = None
            await session.flush()
        except DBAPIError as exc:
            await session.rollback()
            logger.exception(
                "document_finalization_failed document_id=%s stage=document db_detail=%s",
                document_id,
                _safe_db_detail(exc),
            )
            raise DocumentFinalizationError("document") from exc

        user = await session.get(User, document.user_id)
        if user is None:
            await session.rollback()
            raise DocumentProcessingError("Document owner no longer exists")
        try:
            # Checkpoint 3: switch the logical document's active version.
            if operation == "ingest":
                await document_service._activate_version(  # noqa: SLF001
                    session, user, document
                )
                event_type = "version_activated"
            else:
                document.lifecycle_state = (
                    "active" if document.is_active_version else "superseded"
                )
                event_type = "reindex_completed"
            await session.flush()
        except DBAPIError as exc:
            await session.rollback()
            logger.exception(
                "document_finalization_failed document_id=%s stage=activation db_detail=%s",
                document_id,
                _safe_db_detail(exc),
            )
            raise DocumentFinalizationError("activation") from exc

        try:
            # Checkpoint 4: append the lifecycle event and commit atomically.
            session.add(
                KnowledgeDocumentEvent(
                    knowledge_document_id=document.knowledge_document_id,
                    document_id=document.id,
                    actor_user_id=document.user_id,
                    event_type=event_type,
                    event_metadata={
                        "version_number": document.version_number,
                        "chunk_count": len(text_chunks),
                        "background": True,
                    },
                )
            )
            await session.flush()
            await session.commit()
        except DBAPIError as exc:
            await session.rollback()
            logger.exception(
                "document_finalization_failed document_id=%s stage=event db_detail=%s",
                document_id,
                _safe_db_detail(exc),
            )
            raise DocumentFinalizationError("event") from exc

    return {
        "document_id": str(document_id),
        "operation": operation,
        "chunk_count": len(text_chunks),
        "character_count": extraction.character_count,
    }


async def mark_document_job_terminal(
    *,
    document_id: uuid.UUID,
    operation: str,
    error_code: str,
    cancelled: bool = False,
) -> None:
    """Keep initial ingestion failures visible while preserving old re-index data."""
    factory = get_session_factory()
    async with factory() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        if operation == "ingest":
            document.status = DocumentStatus.failed
            document.lifecycle_state = "failed"
            document.is_active_version = False
            document.error_code = "ingestion_cancelled" if cancelled else error_code[:64]
            if cancelled:
                document.error_message = "Document ingestion was cancelled"
            elif error_code.startswith("document_finalization_"):
                stage = error_code.removeprefix("document_finalization_").removesuffix("_failed")
                document.error_message = (
                    f"Document indexing failed during the {stage} finalization step"
                )[:512]
            else:
                document.error_message = "Document ingestion failed after retry attempts"
            document.chunk_count = 0
            document.character_count = 0
            document.processed_at = None
        session.add(
            KnowledgeDocumentEvent(
                knowledge_document_id=document.knowledge_document_id,
                document_id=document.id,
                actor_user_id=document.user_id,
                event_type=("ingestion_cancelled" if cancelled else f"{operation}_failed"),
                event_metadata={"error_code": error_code[:80], "background": True},
            )
        )
        await session.commit()
