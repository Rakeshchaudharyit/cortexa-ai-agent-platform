"""Embedding application service — health and embed helpers for routes."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import Settings
from app.core.logging import request_id_ctx
from app.documents.schemas import EmbeddingStatusResponse
from app.embeddings.base import EmbeddingProvider

logger = logging.getLogger("cortexa.embeddings.service")


@dataclass
class EmbeddingService:
    """Thin façade over the configured embedding provider."""

    settings: Settings
    provider: EmbeddingProvider

    async def status(self) -> EmbeddingStatusResponse:
        request_id = request_id_ctx.get() or "-"
        logger.info(
            "embedding_status_request provider=%s model=%s request_id=%s",
            self.provider.name,
            self.provider.model,
            request_id,
        )
        result = await self.provider.health_check()
        return EmbeddingStatusResponse(
            provider=result.provider,
            model=result.model,
            provider_reachable=result.provider_reachable,
            model_available=result.model_available,
            configured_dimension=result.configured_dimension,
            status=result.status.value,
            message=result.message,
        )

    async def embed(self, text: str) -> list[float]:
        return await self.provider.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self.provider.embed_batch(texts)
