"""Embedding provider protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.embeddings.schemas import EmbeddingHealthResult


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    async def health_check(self) -> EmbeddingHealthResult: ...

    async def embed(self, text: str) -> list[float]: ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
