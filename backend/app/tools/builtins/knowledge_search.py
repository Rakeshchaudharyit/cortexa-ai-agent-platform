"""Knowledge search tool — reuses Phase 4 RetrievalService with ownership checks."""

from __future__ import annotations

from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, Field

from app.tools.base import BaseTool
from app.tools.context import ToolExecutionContext
from app.tools.exceptions import ToolExecutionFailedError, ToolInvalidArgumentsError
from app.tools.schemas import ToolResultPayload

_MAX_LIMIT = 10
_DEFAULT_LIMIT = 5
_EXCERPT_LIMIT = 400


class KnowledgeSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT)


class KnowledgeSearchHit(BaseModel):
    chunk_id: UUID
    document_id: UUID
    title: str
    excerpt: str
    score: float
    citation_id: str
    chunk_index: int
    page_number: int | None = None


class KnowledgeSearchOutput(BaseModel):
    query: str
    results: list[KnowledgeSearchHit]
    count: int


class KnowledgeSearchTool(BaseTool):
    name: ClassVar[str] = "knowledge_search"
    description: ClassVar[str] = (
        "Search the user's uploaded documents for relevant passages. "
        "Prefer this tool for questions about uploaded files. Returns chunk "
        "identifiers, document titles, excerpts, scores, and citation ids."
    )
    version: ClassVar[str] = "1.0.0"
    category: ClassVar[str] = "knowledge"
    input_model: ClassVar[type[BaseModel]] = KnowledgeSearchInput
    output_model: ClassVar[type[BaseModel] | None] = KnowledgeSearchOutput
    timeout_seconds: ClassVar[int] = 60

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResultPayload:
        assert isinstance(arguments, KnowledgeSearchInput)
        retrieval = context.retrieval_service
        if retrieval is None:
            raise ToolExecutionFailedError("Knowledge search is not configured")

        # Load the owning user object for RetrievalService ownership filters.
        from sqlalchemy import select

        from app.models.user import User

        user = await context.session.scalar(select(User).where(User.id == context.user_id))
        if user is None:
            raise ToolExecutionFailedError("User not found for knowledge search")

        document_ids = context.allowed_document_ids
        try:
            retrieved = await retrieval.retrieve(
                context.session,
                user,
                query=arguments.query.strip(),
                top_k=min(arguments.limit, _MAX_LIMIT),
                document_ids=document_ids,
            )
        except Exception as exc:
            # Domain AppErrors from retrieval (e.g. DocumentNotFound) stay typed.
            from app.core.exceptions import AppError

            if isinstance(exc, AppError):
                raise ToolInvalidArgumentsError(exc.message) from exc
            raise ToolExecutionFailedError("Knowledge search failed") from exc

        results: list[KnowledgeSearchHit] = []
        for index, item in enumerate(retrieved, start=1):
            metadata = item.chunk.chunk_metadata or {}
            page_number = metadata.get("page_number")
            page_value = page_number if isinstance(page_number, int) else None
            excerpt = item.chunk.content.strip()
            if len(excerpt) > _EXCERPT_LIMIT:
                excerpt = excerpt[:_EXCERPT_LIMIT].rstrip() + "…"
            results.append(
                KnowledgeSearchHit(
                    chunk_id=item.chunk.id,
                    document_id=item.document.id,
                    title=item.document.original_filename,
                    excerpt=excerpt,
                    score=round(item.similarity, 6),
                    citation_id=f"[{index}]",
                    chunk_index=item.chunk.chunk_index,
                    page_number=page_value,
                )
            )
        payload = KnowledgeSearchOutput(
            query=arguments.query.strip(),
            results=results,
            count=len(results),
        )
        return ToolResultPayload(success=True, data=payload.model_dump(mode="json"))
