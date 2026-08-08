"""Grounded RAG answer generation with citations."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.citations import (
    normalize_grounded_answer,
    select_context_chunks,
)
from app.core.config import Settings
from app.core.logging import request_id_ctx
from app.documents.schemas import RagCitation, RagQueryRequest, RagQueryResponse
from app.llm.schemas import ChatMessage, GenerateRequest, MessageRole
from app.models.user import User
from app.services.llm import LLMService
from app.services.retrieval import RetrievalService, RetrievedChunk

logger = logging.getLogger("cortexa.rag")

_NO_CONTEXT_ANSWER = (
    "I couldn’t find that information in the selected documents. "
    "Try choosing different documents or switch to General Agent mode."
)

_SYSTEM_PROMPT = (
    "You are a grounded question-answering assistant for the user's private documents. "
    "Answer ONLY using the provided context. "
    "Answer directly and concisely. Do not repeat the question. "
    "Prefer a short factual sentence with an inline citation marker. "
    "Cite supporting passages ONLY with bracket markers such as [1], [2]. "
    "Do not invent facts, filenames, or citations. "
    'Do not write "Source:", "Citation ID", filenames, or other citation metadata in prose. '
    "If the context is insufficient, clearly say you could not find it in the selected "
    "documents and do not invent an answer or citation."
)


@dataclass
class RagService:
    """Retrieve relevant chunks and generate a grounded answer."""

    settings: Settings
    retrieval_service: RetrievalService
    llm_service: LLMService

    async def query(
        self,
        session: AsyncSession,
        user: User,
        request: RagQueryRequest,
    ) -> RagQueryResponse:
        request_id = request_id_ctx.get() or "-"
        started = time.perf_counter()
        logger.info(
            "rag_query_start user_id=%s top_k=%s document_filter_count=%s request_id=%s",
            user.id,
            request.top_k,
            len(request.document_ids) if request.document_ids else 0,
            request_id,
        )

        retrieved = await self.retrieval_service.retrieve(
            session,
            user,
            query=request.question,
            top_k=request.top_k,
            document_ids=request.document_ids,
        )
        candidate_count = len(retrieved)
        retrieved = select_context_chunks(
            retrieved, max_chars=self.settings.rag_max_context_characters
        )
        logger.info(
            "rag_context_selected user_id=%s candidate_count=%s selected_count=%s "
            "context_chars=%s request_id=%s",
            user.id,
            candidate_count,
            len(retrieved),
            sum(len(item.chunk.content.strip()) for item in retrieved),
            request_id,
        )

        if not retrieved:
            logger.info(
                "rag_no_result_fallback user_id=%s request_id=%s",
                user.id,
                request_id,
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            return RagQueryResponse(
                answer=_NO_CONTEXT_ANSWER,
                citations=[],
                retrieval_count=0,
                model=self.llm_service.provider.default_model,
                provider=self.llm_service.provider.name,
                grounded=False,
                latency_ms=latency_ms,
            )

        context = self._build_context(retrieved)
        citations = self._build_citations(retrieved)

        generate_request = GenerateRequest(
            messages=[
                ChatMessage(
                    role=MessageRole.user,
                    content=(f"Context:\n{context}\n\n" f"Question:\n{request.question.strip()}"),
                )
            ],
            system=_SYSTEM_PROMPT,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        try:
            generation = await self.llm_service.generate(generate_request)
        except Exception:
            logger.warning(
                "rag_generation_failed user_id=%s retrieval_count=%s request_id=%s",
                user.id,
                len(retrieved),
                request_id,
            )
            raise

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "rag_generation_success user_id=%s retrieval_count=%s latency_ms=%s request_id=%s",
            user.id,
            len(retrieved),
            latency_ms,
            request_id,
        )
        return RagQueryResponse(
            answer=normalize_grounded_answer(
                generation.content, citation_count=len(citations)
            ),
            citations=citations,
            retrieval_count=len(retrieved),
            model=generation.model,
            provider=generation.provider,
            grounded=True,
            latency_ms=latency_ms,
        )

    def _build_context(self, retrieved: list[RetrievedChunk]) -> str:
        max_chars = self.settings.rag_max_context_characters
        parts: list[str] = []
        used = 0
        for index, item in enumerate(retrieved, start=1):
            header = f"[{index}]"
            body = item.chunk.content.strip()
            block = f"{header}\n{body}"
            separator = 2 if parts else 0
            if used + separator + len(block) > max_chars:
                remaining = max_chars - used - separator
                if remaining < 40:
                    break
                block = block[:remaining]
                parts.append(block)
                break
            parts.append(block)
            used += separator + len(block)
        return "\n\n".join(parts)

    def _build_citations(self, retrieved: list[RetrievedChunk]) -> list[RagCitation]:
        excerpt_limit = self.settings.rag_citation_excerpt_characters
        citations: list[RagCitation] = []
        for index, item in enumerate(retrieved, start=1):
            metadata = item.chunk.chunk_metadata or {}
            page_number = metadata.get("page_number")
            page_value: int | None
            if isinstance(page_number, int):
                page_value = page_number
            else:
                page_value = None
            excerpt = item.chunk.content.strip()
            if len(excerpt) > excerpt_limit:
                excerpt = excerpt[:excerpt_limit].rstrip() + "…"
            citations.append(
                RagCitation(
                    citation_id=f"[{index}]",
                    document_id=item.document.id,
                    filename=item.document.original_filename,
                    chunk_id=item.chunk.id,
                    chunk_index=item.chunk.chunk_index,
                    page_number=page_value,
                    excerpt=excerpt,
                    similarity=round(item.similarity, 6),
                )
            )
        return citations
