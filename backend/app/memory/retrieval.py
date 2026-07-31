"""Retrieve and rank relevant active memories for prompt injection."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import request_id_ctx
from app.embeddings.base import EmbeddingProvider
from app.memory.repository import MemoryRepository
from app.memory.schemas import RetrievedMemoryView
from app.models.memory import UserMemory
from app.models.user import User

logger = logging.getLogger("cortexa.memory.retrieval")

_TOKEN = re.compile(r"[a-z0-9_]+", re.IGNORECASE)


@dataclass
class MemoryRetriever:
    settings: Settings
    repository: MemoryRepository
    embedding_provider: EmbeddingProvider | None = None

    async def retrieve(
        self,
        session: AsyncSession,
        user: User,
        *,
        query: str,
        conversation_context: str | None = None,
        limit: int | None = None,
    ) -> list[RetrievedMemoryView]:
        started = time.perf_counter()
        request_id = request_id_ctx.get() or "-"
        max_results = limit or self.settings.memory_max_retrieval_results
        min_score = self.settings.memory_min_relevance_score
        query_text = " ".join(
            part for part in [query.strip(), (conversation_context or "").strip()] if part
        )
        logger.info(
            "memory_retrieval_started user_id=%s query_chars=%s request_id=%s",
            user.id,
            len(query_text),
            request_id,
        )

        try:
            candidates = await self.repository.list_retrievable(session, user)
        except Exception:
            logger.info(
                "memory_retrieval_failed user_id=%s request_id=%s",
                user.id,
                request_id,
            )
            return []

        if not candidates or not query_text:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "memory_retrieval_completed user_id=%s considered=%s selected=0 "
                "duration_ms=%s request_id=%s",
                user.id,
                len(candidates),
                duration_ms,
                request_id,
            )
            return []

        query_embedding: list[float] | None = None
        if self.embedding_provider is not None:
            try:
                query_embedding = await self.embedding_provider.embed(
                    query_text[: self.settings.embedding_max_input_characters]
                )
            except Exception:
                query_embedding = None

        scored: list[RetrievedMemoryView] = []
        for memory in candidates:
            relevance = self._score(memory, query_text, query_embedding)
            if relevance < min_score:
                continue
            scored.append(
                RetrievedMemoryView(
                    id=memory.id,
                    title=memory.title,
                    content=memory.content,
                    category=memory.category,
                    relevance=relevance,
                    importance=float(memory.importance),
                )
            )

        scored.sort(key=lambda item: (item.relevance * 0.7 + item.importance * 0.3), reverse=True)
        deduped = self._dedupe(scored)
        selected = deduped[:max_results]

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "memory_retrieval_completed user_id=%s considered=%s selected=%s "
            "duration_ms=%s request_id=%s",
            user.id,
            len(candidates),
            len(selected),
            duration_ms,
            request_id,
        )
        return selected

    def _score(
        self,
        memory: UserMemory,
        query: str,
        query_embedding: list[float] | None,
    ) -> float:
        semantic = 0.0
        if query_embedding is not None and memory.embedding is not None:
            semantic = _cosine(query_embedding, list(memory.embedding))
        keyword = _keyword_overlap(query, f"{memory.title} {memory.content}")
        recency = 0.1
        if memory.last_used_at is not None:
            recency = 0.2
        frequency = min(0.15, 0.02 * float(memory.use_count or 0))
        # Blend: prefer semantic when available, else keyword.
        base = semantic if semantic > 0 else keyword
        return min(1.0, base * 0.75 + float(memory.importance) * 0.15 + recency + frequency)

    def _dedupe(self, items: list[RetrievedMemoryView]) -> list[RetrievedMemoryView]:
        seen: set[str] = set()
        result: list[RetrievedMemoryView] = []
        for item in items:
            key = re.sub(r"\s+", " ", item.content.lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return float(max(0.0, min(1.0, dot / (na * nb))))


def _keyword_overlap(query: str, content: str) -> float:
    q_tokens = {t.lower() for t in _TOKEN.findall(query) if len(t) > 2}
    c_tokens = {t.lower() for t in _TOKEN.findall(content) if len(t) > 2}
    if not q_tokens or not c_tokens:
        return 0.0
    overlap = len(q_tokens & c_tokens)
    return min(1.0, overlap / max(1, len(q_tokens)))
