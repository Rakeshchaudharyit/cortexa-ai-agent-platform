"""Document ingestion, listing, and deletion service."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.logging import request_id_ctx
from app.documents.chunking import ChunkingService
from app.documents.exceptions import (
    DocumentNotFoundError,
    DocumentProcessingError,
    DuplicateDocumentError,
)
from app.documents.extraction import ExtractionService
from app.documents.schemas import DocumentListResponse, DocumentResponse
from app.documents.validation import validate_upload
from app.embeddings.base import EmbeddingProvider
from app.models.document import Document, DocumentChunk
from app.models.enums import DocumentStatus
from app.models.user import User
from app.storage.base import ObjectStorage
from app.storage.exceptions import StorageError

logger = logging.getLogger("cortexa.documents.service")


@dataclass
class DocumentService:
    """Synchronous (request-scoped) document ingestion and ownership APIs."""

    settings: Settings
    storage: ObjectStorage
    extraction_service: ExtractionService
    chunking_service: ChunkingService
    embedding_provider: EmbeddingProvider

    async def ingest(
        self,
        session: AsyncSession,
        user: User,
        *,
        filename: str | None,
        content_type: str | None,
        data: bytes,
    ) -> Document:
        request_id = request_id_ctx.get() or "-"
        logger.info(
            "document_upload_start user_id=%s file_size=%s request_id=%s",
            user.id,
            len(data),
            request_id,
        )

        validated = validate_upload(
            filename=filename,
            content_type=content_type,
            data=data,
            settings=self.settings,
        )

        existing = await session.scalar(
            select(Document.id).where(
                Document.user_id == user.id,
                Document.checksum_sha256 == validated.checksum_sha256,
            )
        )
        if existing is not None:
            logger.info(
                "document_upload_rejected category=duplicate user_id=%s request_id=%s",
                user.id,
                request_id,
            )
            raise DuplicateDocumentError()

        document_id = uuid.uuid4()
        storage_key = f"{user.id}/{document_id}{validated.extension}"
        stored_key = await self.storage.put_bytes(key=storage_key, data=validated.data)

        document = Document(
            id=document_id,
            user_id=user.id,
            filename=f"{document_id}{validated.extension}",
            original_filename=validated.original_filename,
            media_type=validated.media_type,
            file_size_bytes=validated.file_size_bytes,
            checksum_sha256=validated.checksum_sha256,
            storage_key=stored_key,
            status=DocumentStatus.processing,
        )
        session.add(document)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            await self._safe_delete_storage(stored_key)
            logger.info(
                "document_upload_rejected category=duplicate_integrity user_id=%s request_id=%s",
                user.id,
                request_id,
            )
            raise DuplicateDocumentError() from exc

        await session.refresh(document)

        try:
            extraction = self.extraction_service.extract(
                data=validated.data,
                media_type=validated.media_type,
                filename=validated.original_filename,
            )
            text_chunks = self.chunking_service.chunk(
                extraction,
                document_id=str(document.id),
                source_filename=validated.original_filename,
            )
            logger.info(
                "document_chunking_summary document_id=%s chunk_count=%s character_count=%s "
                "request_id=%s",
                document.id,
                len(text_chunks),
                extraction.character_count,
                request_id,
            )

            batch_size = self.settings.embedding_batch_size
            embeddings: list[list[float]] = []
            for start in range(0, len(text_chunks), batch_size):
                batch = text_chunks[start : start + batch_size]
                logger.info(
                    "embedding_batch_start document_id=%s batch_index=%s batch_size=%s "
                    "request_id=%s",
                    document.id,
                    start // batch_size,
                    len(batch),
                    request_id,
                )
                vectors = await self.embedding_provider.embed_batch(
                    [chunk.content for chunk in batch]
                )
                if len(vectors) != len(batch):
                    raise DocumentProcessingError("Embedding batch length mismatch")
                embeddings.extend(vectors)
                logger.info(
                    "embedding_batch_success document_id=%s batch_index=%s request_id=%s",
                    document.id,
                    start // batch_size,
                    request_id,
                )

            for chunk, vector in zip(text_chunks, embeddings, strict=True):
                content_sha = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
                session.add(
                    DocumentChunk(
                        document_id=document.id,
                        user_id=user.id,
                        chunk_index=chunk.index,
                        content=chunk.content,
                        content_sha256=content_sha,
                        character_count=chunk.character_count,
                        embedding=vector,
                        chunk_metadata=dict(chunk.metadata),
                    )
                )

            document.status = DocumentStatus.ready
            document.chunk_count = len(text_chunks)
            document.character_count = extraction.character_count
            document.processed_at = datetime.now(UTC)
            document.error_code = None
            document.error_message = None
            await session.commit()
            await session.refresh(document)
            logger.info(
                "document_ingestion_complete document_id=%s user_id=%s chunk_count=%s "
                "request_id=%s",
                document.id,
                user.id,
                document.chunk_count,
                request_id,
            )
            return document
        except Exception as exc:
            await session.rollback()
            await self._mark_failed(session, document=document, error=exc)
            await self._safe_delete_storage(stored_key)
            if isinstance(exc, AppError):
                raise
            logger.warning(
                "document_ingestion_failed document_id=%s category=unexpected request_id=%s",
                document.id,
                request_id,
            )
            raise DocumentProcessingError() from exc

    async def list_documents(
        self,
        session: AsyncSession,
        user: User,
        *,
        limit: int = 20,
        offset: int = 0,
        status_filter: DocumentStatus | None = None,
        filename: str | None = None,
    ) -> DocumentListResponse:
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        filters = [Document.user_id == user.id]
        if status_filter is not None:
            filters.append(Document.status == status_filter)
        if filename is not None and filename.strip():
            filters.append(Document.original_filename.ilike(f"%{filename.strip()}%"))

        total = await session.scalar(select(func.count()).select_from(Document).where(*filters))
        result = await session.scalars(
            select(Document)
            .where(*filters)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items = [self.to_response(document) for document in result.all()]
        return DocumentListResponse(
            items=items,
            total=int(total or 0),
            limit=limit,
            offset=offset,
        )

    async def get_document(
        self,
        session: AsyncSession,
        user: User,
        document_id: uuid.UUID,
    ) -> Document:
        document = await session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user.id,
            )
        )
        if document is None:
            raise DocumentNotFoundError()
        return document

    async def delete_document(
        self,
        session: AsyncSession,
        user: User,
        document_id: uuid.UUID,
    ) -> None:
        document = await self.get_document(session, user, document_id)
        storage_key = document.storage_key
        await session.delete(document)
        await session.commit()
        logger.info(
            "document_deleted document_id=%s user_id=%s",
            document_id,
            user.id,
        )
        await self._safe_delete_storage(storage_key)

    def to_response(self, document: Document) -> DocumentResponse:
        return DocumentResponse(
            id=document.id,
            original_filename=document.original_filename,
            media_type=document.media_type,
            file_size_bytes=document.file_size_bytes,
            status=document.status,
            chunk_count=document.chunk_count,
            character_count=document.character_count,
            created_at=document.created_at,
            updated_at=document.updated_at,
            processed_at=document.processed_at,
            error_code=document.error_code,
            error_message=document.error_message,
            processing_mode="synchronous",
        )

    async def _mark_failed(
        self,
        session: AsyncSession,
        *,
        document: Document,
        error: BaseException,
    ) -> None:
        code, message = self._safe_error_fields(error)
        fresh = await session.get(Document, document.id)
        if fresh is None:
            return
        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == fresh.id))
        fresh.status = DocumentStatus.failed
        fresh.error_code = code
        fresh.error_message = message
        fresh.chunk_count = 0
        fresh.character_count = 0
        fresh.processed_at = None
        await session.commit()
        logger.info(
            "document_marked_failed document_id=%s error_code=%s",
            fresh.id,
            code,
        )

    @staticmethod
    def _safe_error_fields(error: BaseException) -> tuple[str, str]:
        if isinstance(error, AppError):
            return error.code, error.message[:512]
        return "document_processing_failed", "Document processing failed"

    async def _safe_delete_storage(self, key: str) -> None:
        try:
            await self.storage.delete(key=key)
        except StorageError:
            logger.warning("document_storage_delete_failed")
        except Exception:  # noqa: BLE001
            logger.warning("document_storage_delete_failed category=unexpected")
