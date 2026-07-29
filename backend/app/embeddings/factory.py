"""Embedding provider factory."""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.providers.ollama import OllamaEmbeddingProvider


def create_embedding_provider(
    settings: Settings,
    http_client: httpx.AsyncClient,
) -> EmbeddingProvider:
    provider = settings.embedding_provider.strip().lower()
    if provider == "ollama":
        return OllamaEmbeddingProvider(settings=settings, http_client=http_client)
    raise ValueError(f"Unsupported embedding provider: {provider}")
