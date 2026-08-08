"""Semantic document retrieval with pgvector cosine distance."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.logging import request_id_ctx
from app.documents.exceptions import DocumentNotFoundError, RetrievalError
from app.embeddings.base import EmbeddingProvider
from app.models.document import Document, DocumentChunk
from app.models.enums import DocumentStatus
from app.models.user import User

logger = logging.getLogger("cortexa.retrieval")


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: DocumentChunk
    document: Document
    similarity: float


@dataclass
class RetrievalService:
    """User-scoped semantic retrieval over ready document chunks."""

    settings: Settings
    embedding_provider: EmbeddingProvider

    async def retrieve(
        self,
        session: AsyncSession,
        user: User,
        *,
        query: str,
        top_k: int | None = None,
        document_ids: list[uuid.UUID] | None = None,
        min_similarity: float | None = None,
    ) -> list[RetrievedChunk]:
        request_id = request_id_ctx.get() or "-"
        cleaned = query.strip()
        if not cleaned:
            raise AppError(
                code="invalid_query",
                message="Query cannot be blank",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if len(cleaned) > self.settings.rag_max_query_characters:
            raise AppError(
                code="query_too_long",
                message=(
                    "Query exceeds the maximum allowed length "
                    f"({self.settings.rag_max_query_characters} characters)"
                ),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        resolved_top_k = top_k if top_k is not None else self.settings.rag_default_top_k
        resolved_top_k = max(1, min(resolved_top_k, self.settings.rag_max_top_k))
        threshold = (
            min_similarity if min_similarity is not None else self.settings.rag_min_similarity
        )
        threshold = max(0.0, min(1.0, threshold))

        if document_ids:
            unique_ids = list(dict.fromkeys(document_ids))
            found_rows = await session.scalars(
                select(Document.id).where(
                    Document.user_id == user.id,
                    Document.id.in_(unique_ids),
                    Document.archived_at.is_(None),
                    Document.is_active_version.is_(True),
                )
            )
            found = set(found_rows.all())
            if len(found) != len(unique_ids):
                raise DocumentNotFoundError()

        logger.info(
            "retrieval_start user_id=%s top_k=%s document_filter_count=%s request_id=%s",
            user.id,
            resolved_top_k,
            len(document_ids) if document_ids else 0,
            request_id,
        )

        try:
            query_embedding = await self.embedding_provider.embed(cleaned)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "retrieval_embedding_failed category=unexpected request_id=%s",
                request_id,
            )
            raise RetrievalError() from exc

        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        similarity_expr = (1 - distance).label("similarity")

        stmt = (
            select(DocumentChunk, Document, similarity_expr)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.user_id == user.id,
                Document.user_id == user.id,
                Document.status == DocumentStatus.ready,
                Document.archived_at.is_(None),
                    Document.is_active_version.is_(True),
            )
            .order_by(
                similarity_expr.desc(),
                DocumentChunk.chunk_index.asc(),
                DocumentChunk.id.asc(),
            )
            .limit(resolved_top_k)
        )
        if document_ids:
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))

        try:
            rows = (await session.execute(stmt)).all()
        except Exception as exc:  # noqa: BLE001
            logger.warning("retrieval_query_failed category=unexpected request_id=%s", request_id)
            raise RetrievalError() from exc

        results: list[RetrievedChunk] = []
        for chunk, document, similarity in rows:
            score = float(similarity)
            if score < threshold:
                continue
            results.append(
                RetrievedChunk(
                    chunk=chunk,
                    document=document,
                    similarity=score,
                )
            )

        logger.info(
            "retrieval_complete user_id=%s retrieval_count=%s request_id=%s",
            user.id,
            len(results),
            request_id,
        )
        return results
