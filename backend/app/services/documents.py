"""Document ingestion, listing, and deletion service."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
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
from app.documents.schemas import (
    DocumentFolderCreate,
    DocumentFolderListResponse,
    DocumentFolderResponse,
    DocumentListResponse,
    DocumentMetadataUpdate,
    DocumentResponse,
    DocumentTimelineResponse,
    DocumentVersionCompareResponse,
    DocumentVersionHistoryResponse,
    DocumentVersionSummary,
    KnowledgeDocumentEventResponse,
)
from app.documents.validation import validate_upload
from app.embeddings.base import EmbeddingProvider
from app.models.document import (
    Document, DocumentChunk, DocumentFolder, KnowledgeDocument, KnowledgeDocumentEvent,
)
from app.models.enums import DocumentStatus
from app.models.job import BackgroundJob
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

    async def create_pending_upload(
        self,
        session: AsyncSession,
        user: User,
        *,
        filename: str | None,
        content_type: str | None,
        data: bytes,
        folder_id: uuid.UUID | None = None,
        supersedes_document_id: uuid.UUID | None = None,
    ) -> Document:
        """Validate and durably store an upload without processing it in the API request."""
        request_id = request_id_ctx.get() or "-"
        validated = validate_upload(
            filename=filename, content_type=content_type, data=data, settings=self.settings
        )

        folder = None
        if folder_id is not None:
            folder = await session.scalar(
                select(DocumentFolder).where(
                    DocumentFolder.id == folder_id, DocumentFolder.user_id == user.id
                )
            )
            if folder is None:
                raise AppError(
                    code="document_folder_not_found",
                    message="Document folder not found",
                    status_code=404,
                )

        superseded = None
        if supersedes_document_id is not None:
            superseded = await self.get_document(session, user, supersedes_document_id)

        existing = await session.scalar(
            select(Document.id).where(
                Document.user_id == user.id,
                Document.checksum_sha256 == validated.checksum_sha256,
                Document.archived_at.is_(None),
            )
        )
        if existing is not None and superseded is None:
            raise DuplicateDocumentError()

        document_id = uuid.uuid4()
        storage_key = f"{user.id}/{document_id}{validated.extension}"
        stored_key = await self.storage.put_bytes(key=storage_key, data=validated.data)

        if superseded is not None:
            knowledge = await session.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == superseded.knowledge_document_id,
                    KnowledgeDocument.user_id == user.id,
                )
            )
            if knowledge is None:
                await self._safe_delete_storage(stored_key)
                raise AppError(
                    code="knowledge_document_not_found",
                    message="Knowledge document not found",
                    status_code=404,
                )
        else:
            knowledge = KnowledgeDocument(
                user_id=user.id,
                folder_id=folder.id if folder else None,
                title=validated.original_filename,
                tags=[],
            )
            session.add(knowledge)
            await session.flush()

        next_version_number = 1
        if superseded is not None:
            current_max = await session.scalar(
                select(func.max(Document.version_number)).where(
                    Document.knowledge_document_id == knowledge.id
                )
            )
            next_version_number = int(current_max or 0) + 1

        document = Document(
            id=document_id,
            user_id=user.id,
            filename=f"{document_id}{validated.extension}",
            original_filename=validated.original_filename,
            media_type=validated.media_type,
            file_size_bytes=validated.file_size_bytes,
            checksum_sha256=validated.checksum_sha256,
            storage_key=stored_key,
            status=DocumentStatus.pending,
            knowledge_document_id=knowledge.id,
            lifecycle_state="processing",
            is_active_version=False,
            folder_id=folder.id if folder else (superseded.folder_id if superseded else None),
            title=superseded.title if superseded else validated.original_filename,
            tags=list(superseded.tags or []) if superseded else [],
            version_number=next_version_number,
            supersedes_document_id=superseded.id if superseded else None,
        )
        session.add(document)
        session.add(
            KnowledgeDocumentEvent(
                knowledge_document_id=knowledge.id,
                document_id=document.id,
                actor_user_id=user.id,
                event_type="version_queued" if superseded else "document_queued",
                event_metadata={"version_number": document.version_number},
            )
        )
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            await self._safe_delete_storage(stored_key)
            raise DuplicateDocumentError() from exc
        await session.refresh(document)
        logger.info(
            "document_upload_queued document_id=%s user_id=%s request_id=%s",
            document.id, user.id, request_id,
        )
        return document

    async def list_documents(
        self,
        session: AsyncSession,
        user: User,
        *,
        limit: int = 20,
        offset: int = 0,
        status_filter: DocumentStatus | None = None,
        filename: str | None = None,
        folder_id: uuid.UUID | None = None,
        archived: bool = False,
    ) -> DocumentListResponse:
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        filters = [Document.user_id == user.id]
        filters.append(Document.archived_at.is_not(None) if archived else Document.archived_at.is_(None))
        if status_filter is not None:
            filters.append(Document.status == status_filter)
        if filename is not None and filename.strip():
            filters.append(Document.original_filename.ilike(f"%{filename.strip()}%"))
        if folder_id is not None:
            filters.append(Document.folder_id == folder_id)

        total = await session.scalar(select(func.count()).select_from(Document).where(*filters))
        result = await session.scalars(
            select(Document)
            .where(*filters)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(limit)
            .offset(offset)
        )
        documents = list(result.all())
        job_ids = [item.background_job_id for item in documents if item.background_job_id is not None]
        jobs: dict[uuid.UUID, BackgroundJob] = {}
        if job_ids:
            job_rows = (await session.scalars(
                select(BackgroundJob).where(BackgroundJob.id.in_(job_ids))
            )).all()
            jobs = {item.id: item for item in job_rows}
        items = [self.to_response(document, jobs.get(document.background_job_id)) for document in documents]
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

    async def get_background_job(
        self, session: AsyncSession, document: Document
    ) -> BackgroundJob | None:
        if document.background_job_id is None:
            return None
        return await session.get(BackgroundJob, document.background_job_id)

    async def list_folders(self, session: AsyncSession, user: User) -> DocumentFolderListResponse:
        rows = (await session.execute(
            select(DocumentFolder, func.count(Document.id))
            .outerjoin(Document, (Document.folder_id == DocumentFolder.id) & (Document.archived_at.is_(None)))
            .where(DocumentFolder.user_id == user.id)
            .group_by(DocumentFolder.id)
            .order_by(DocumentFolder.name.asc())
        )).all()
        items = [
            DocumentFolderResponse(
                id=folder.id, name=folder.name, description=folder.description,
                document_count=int(count or 0), created_at=folder.created_at, updated_at=folder.updated_at
            ) for folder, count in rows
        ]
        return DocumentFolderListResponse(items=items, total=len(items))

    async def create_folder(
        self, session: AsyncSession, user: User, payload: DocumentFolderCreate
    ) -> DocumentFolderResponse:
        folder = DocumentFolder(user_id=user.id, name=payload.name, description=payload.description)
        session.add(folder)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise AppError(code="document_folder_exists", message="A folder with this name already exists", status_code=409) from exc
        await session.refresh(folder)
        return DocumentFolderResponse(
            id=folder.id, name=folder.name, description=folder.description, document_count=0,
            created_at=folder.created_at, updated_at=folder.updated_at
        )

    async def delete_folder(self, session: AsyncSession, user: User, folder_id: uuid.UUID) -> None:
        folder = await session.scalar(select(DocumentFolder).where(
            DocumentFolder.id == folder_id, DocumentFolder.user_id == user.id
        ))
        if folder is None:
            raise AppError(code="document_folder_not_found", message="Document folder not found", status_code=404)
        await session.delete(folder)
        await session.commit()

    async def update_metadata(
        self, session: AsyncSession, user: User, document_id: uuid.UUID, payload: DocumentMetadataUpdate
    ) -> Document:
        document = await self.get_document(session, user, document_id)
        if payload.folder_id is not None:
            folder = await session.scalar(select(DocumentFolder.id).where(
                DocumentFolder.id == payload.folder_id, DocumentFolder.user_id == user.id
            ))
            if folder is None:
                raise AppError(code="document_folder_not_found", message="Document folder not found", status_code=404)
        document.title = payload.title
        document.folder_id = payload.folder_id
        document.tags = payload.tags
        if document.is_active_version and document.knowledge_document_id is not None:
            knowledge = await session.get(KnowledgeDocument, document.knowledge_document_id)
            if knowledge is not None:
                knowledge.title = document.title or document.original_filename
                knowledge.folder_id = document.folder_id
                knowledge.tags = list(document.tags or [])
        await self._add_event(
            session, document=document, actor_user_id=user.id, event_type="metadata_updated",
            metadata={"version_number": document.version_number},
        )
        await session.commit()
        await session.refresh(document)
        return document

    async def set_archived(
        self, session: AsyncSession, user: User, document_id: uuid.UUID, *, archived: bool
    ) -> Document:
        document = await self.get_document(session, user, document_id)
        if archived and document.background_job_id is not None:
            background_job = await session.get(BackgroundJob, document.background_job_id)
            if background_job is not None and background_job.status in {"queued", "running", "retrying"}:
                raise AppError(
                    code="document_job_active",
                    message="Wait for background processing to finish or cancel the job first",
                    status_code=409,
                )
        if archived:
            document.archived_at = datetime.now(UTC)
            document.lifecycle_state = "archived"
            if document.is_active_version:
                document.is_active_version = False
                knowledge = await session.get(KnowledgeDocument, document.knowledge_document_id)
                if knowledge is not None:
                    knowledge.active_version_id = None
            event_type = "version_archived"
        else:
            if document.status != DocumentStatus.ready:
                raise AppError(code="document_not_ready", message="Only ready versions can be restored", status_code=409)
            await self._activate_version(session, user, document)
            event_type = "version_restored"
        await self._add_event(session, document=document, actor_user_id=user.id, event_type=event_type)
        await session.commit()
        await session.refresh(document)
        logger.info("document_archive_changed document_id=%s user_id=%s archived=%s", document.id, user.id, archived)
        return document

    async def activate_version(
        self, session: AsyncSession, user: User, document_id: uuid.UUID
    ) -> Document:
        document = await self.get_document(session, user, document_id)
        if document.status != DocumentStatus.ready:
            raise AppError(code="document_not_ready", message="Only ready versions can be activated", status_code=409)
        await self._activate_version(session, user, document)
        await self._add_event(
            session, document=document, actor_user_id=user.id, event_type="version_activated",
            metadata={"version_number": document.version_number},
        )
        await session.commit()
        await session.refresh(document)
        return document

    async def _activate_version(self, session: AsyncSession, user: User, document: Document) -> None:
        if document.knowledge_document_id is None:
            raise AppError(code="knowledge_document_not_found", message="Knowledge document not found", status_code=404)
        await session.execute(
            update(Document)
            .where(
                Document.knowledge_document_id == document.knowledge_document_id,
                Document.user_id == user.id,
                Document.id != document.id,
                Document.is_active_version.is_(True),
            )
            .values(is_active_version=False, lifecycle_state="superseded")
        )
        document.archived_at = None
        document.is_active_version = True
        document.lifecycle_state = "active"
        knowledge = await session.get(KnowledgeDocument, document.knowledge_document_id)
        if knowledge is None:
            raise AppError(code="knowledge_document_not_found", message="Knowledge document not found", status_code=404)
        knowledge.active_version_id = document.id
        knowledge.title = document.title or document.original_filename
        knowledge.folder_id = document.folder_id
        knowledge.tags = list(document.tags or [])

    async def reindex_owned_document(
        self, session: AsyncSession, user: User, document_id: uuid.UUID
    ) -> Document:
        document = await self.get_document(session, user, document_id)
        document.lifecycle_state = "processing"
        await self._add_event(
            session, document=document, actor_user_id=user.id, event_type="reindex_started",
            metadata={"version_number": document.version_number},
        )
        await session.commit()
        try:
            document = await self.reprocess_document(session, document)
            document.lifecycle_state = "active" if document.is_active_version else "superseded"
            await self._add_event(
                session, document=document, actor_user_id=user.id, event_type="reindex_completed",
                metadata={"chunk_count": document.chunk_count},
            )
            await session.commit()
            await session.refresh(document)
            return document
        except Exception as exc:
            await self._add_event(
                session, document=document, actor_user_id=user.id, event_type="reindex_failed",
                metadata={"error_type": type(exc).__name__},
            )
            await session.commit()
            raise

    async def get_version_history(
        self, session: AsyncSession, user: User, document_id: uuid.UUID
    ) -> DocumentVersionHistoryResponse:
        document = await self.get_document(session, user, document_id)
        if document.knowledge_document_id is None:
            raise AppError(code="knowledge_document_not_found", message="Knowledge document not found", status_code=404)
        knowledge = await session.get(KnowledgeDocument, document.knowledge_document_id)
        versions = (await session.scalars(
            select(Document).where(
                Document.knowledge_document_id == document.knowledge_document_id,
                Document.user_id == user.id,
            ).order_by(Document.version_number.desc(), Document.created_at.desc())
        )).all()
        return DocumentVersionHistoryResponse(
            knowledge_document_id=document.knowledge_document_id,
            title=(knowledge.title if knowledge else (document.title or document.original_filename)),
            active_version_id=knowledge.active_version_id if knowledge else None,
            versions=[self._version_summary(item) for item in versions],
        )

    async def get_timeline(
        self, session: AsyncSession, user: User, document_id: uuid.UUID
    ) -> DocumentTimelineResponse:
        document = await self.get_document(session, user, document_id)
        if document.knowledge_document_id is None:
            raise AppError(code="knowledge_document_not_found", message="Knowledge document not found", status_code=404)
        events = (await session.scalars(
            select(KnowledgeDocumentEvent)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeDocumentEvent.knowledge_document_id)
            .where(
                KnowledgeDocumentEvent.knowledge_document_id == document.knowledge_document_id,
                KnowledgeDocument.user_id == user.id,
            )
            .order_by(KnowledgeDocumentEvent.created_at.desc())
        )).all()
        return DocumentTimelineResponse(
            knowledge_document_id=document.knowledge_document_id,
            items=[KnowledgeDocumentEventResponse(
                id=item.id, document_id=item.document_id, event_type=item.event_type,
                metadata=dict(item.event_metadata or {}), created_at=item.created_at,
            ) for item in events],
        )

    async def compare_versions(
        self, session: AsyncSession, user: User, left_id: uuid.UUID, right_id: uuid.UUID
    ) -> DocumentVersionCompareResponse:
        left = await self.get_document(session, user, left_id)
        right = await self.get_document(session, user, right_id)
        if left.knowledge_document_id != right.knowledge_document_id:
            raise AppError(code="version_lineage_mismatch", message="Versions do not belong to the same knowledge document", status_code=409)
        changed: list[str] = []
        for name in ("title", "tags", "folder_id", "original_filename", "media_type", "checksum_sha256"):
            if getattr(left, name) != getattr(right, name):
                changed.append(name)
        return DocumentVersionCompareResponse(
            left=self._version_summary(left), right=self._version_summary(right),
            changed_fields=changed,
            chunk_count_delta=right.chunk_count - left.chunk_count,
            character_count_delta=right.character_count - left.character_count,
        )

    async def delete_document(
        self,
        session: AsyncSession,
        user: User,
        document_id: uuid.UUID,
    ) -> None:
        document = await self.get_document(session, user, document_id)
        storage_key = document.storage_key
        knowledge_id = document.knowledge_document_id
        was_active = document.is_active_version
        if document.background_job_id is not None:
            background_job = await session.get(BackgroundJob, document.background_job_id)
            if background_job is not None and background_job.status in {"queued", "running", "retrying"}:
                background_job.cancellation_requested = True
                if background_job.status in {"queued", "retrying"}:
                    background_job.status = "cancelled"
                    background_job.status_message = "Cancelled because the document was deleted"
                    background_job.finished_at = datetime.now(UTC)
        await session.delete(document)
        await session.flush()

        if knowledge_id is not None:
            remaining = (await session.scalars(
                select(Document).where(
                    Document.knowledge_document_id == knowledge_id,
                    Document.user_id == user.id,
                ).order_by(Document.version_number.desc(), Document.created_at.desc())
            )).all()
            knowledge = await session.get(KnowledgeDocument, knowledge_id)
            if not remaining:
                if knowledge is not None:
                    await session.delete(knowledge)
            elif was_active:
                replacement = next(
                    (item for item in remaining if item.status == DocumentStatus.ready and item.archived_at is None),
                    None,
                )
                if replacement is not None:
                    await self._activate_version(session, user, replacement)
                    await self._add_event(
                        session, document=replacement, actor_user_id=user.id,
                        event_type="active_version_reassigned",
                        metadata={"deleted_version_id": str(document_id)},
                    )
                elif knowledge is not None:
                    knowledge.active_version_id = None

        await session.commit()
        logger.info(
            "document_deleted document_id=%s user_id=%s",
            document_id,
            user.id,
        )
        await self._safe_delete_storage(storage_key)

    def to_response(
        self, document: Document, background_job: BackgroundJob | None = None
    ) -> DocumentResponse:
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
            title=document.title,
            folder_id=document.folder_id,
            folder_name=None,
            tags=list(document.tags or []),
            version_number=document.version_number,
            knowledge_document_id=document.knowledge_document_id,
            lifecycle_state=document.lifecycle_state,
            is_active_version=document.is_active_version,
            supersedes_document_id=document.supersedes_document_id,
            archived_at=document.archived_at,
            is_archived=document.archived_at is not None,
            processing_mode="background" if document.background_job_id else "synchronous",
            background_job_id=document.background_job_id,
            job_status=background_job.status if background_job else None,
            job_progress_percent=background_job.progress_percent if background_job else None,
            job_status_message=background_job.status_message if background_job else None,
        )

    @staticmethod
    def _version_summary(document: Document) -> DocumentVersionSummary:
        return DocumentVersionSummary(
            id=document.id, version_number=document.version_number, title=document.title,
            original_filename=document.original_filename, lifecycle_state=document.lifecycle_state,
            is_active_version=document.is_active_version, status=document.status,
            chunk_count=document.chunk_count, character_count=document.character_count,
            created_at=document.created_at, processed_at=document.processed_at,
            archived_at=document.archived_at,
        )

    async def _add_event(
        self, session: AsyncSession, *, document: Document, actor_user_id: uuid.UUID,
        event_type: str, metadata: dict[str, object] | None = None,
    ) -> None:
        if document.knowledge_document_id is None:
            return
        session.add(KnowledgeDocumentEvent(
            knowledge_document_id=document.knowledge_document_id, document_id=document.id,
            actor_user_id=actor_user_id, event_type=event_type, event_metadata=metadata or {},
        ))

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
        fresh.lifecycle_state = "failed"
        fresh.is_active_version = False
        await self._add_event(
            session, document=fresh, actor_user_id=fresh.user_id, event_type="version_failed",
            metadata={"error_code": code},
        )
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

    async def reprocess_document(self, session: AsyncSession, document: Document) -> Document:
        """Admin reprocess: reload bytes from storage and rebuild chunks/embeddings."""
        request_id = request_id_ctx.get() or "-"
        try:
            data = await self.storage.get_bytes(key=document.storage_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "document_reprocess_storage_failed document_id=%s request_id=%s",
                document.id,
                request_id,
            )
            raise DocumentProcessingError() from exc

        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        document.status = DocumentStatus.processing
        document.error_code = None
        document.error_message = None
        document.chunk_count = 0
        document.character_count = 0
        document.processed_at = None
        await session.flush()

        try:
            extraction = self.extraction_service.extract(
                data=data,
                media_type=document.media_type,
                filename=document.original_filename,
            )
            text_chunks = self.chunking_service.chunk(
                extraction,
                document_id=str(document.id),
                source_filename=document.original_filename,
            )
            batch_size = self.settings.embedding_batch_size
            embeddings: list[list[float]] = []
            for start in range(0, len(text_chunks), batch_size):
                batch = text_chunks[start : start + batch_size]
                vectors = await self.embedding_provider.embed_batch(
                    [chunk.content for chunk in batch]
                )
                if len(vectors) != len(batch):
                    raise DocumentProcessingError("Embedding batch length mismatch")
                embeddings.extend(vectors)

            for chunk, vector in zip(text_chunks, embeddings, strict=True):
                content_sha = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
                session.add(
                    DocumentChunk(
                        document_id=document.id,
                        user_id=document.user_id,
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
            await session.flush()
            logger.info(
                "document_reprocess_complete document_id=%s chunk_count=%s request_id=%s",
                document.id,
                document.chunk_count,
                request_id,
            )
            return document
        except Exception as exc:
            code, message = self._safe_error_fields(exc)
            document.status = DocumentStatus.failed
            document.error_code = code
            document.error_message = message
            document.chunk_count = 0
            document.character_count = 0
            document.processed_at = None
            await session.flush()
            if isinstance(exc, AppError):
                raise
            raise DocumentProcessingError() from exc

    async def _safe_delete_storage(self, key: str) -> None:
        try:
            await self.storage.delete(key=key)
        except StorageError:
            logger.warning("document_storage_delete_failed")
        except Exception:  # noqa: BLE001
            logger.warning("document_storage_delete_failed category=unexpected")
