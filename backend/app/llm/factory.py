"""LLM provider factory."""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.llm.base import LLMProvider
from app.llm.providers.ollama import OllamaProvider


def create_llm_provider(settings: Settings, http_client: httpx.AsyncClient) -> LLMProvider:
    """Resolve the configured LLM provider implementation.

    Future providers (OpenAI, Anthropic, …) can be added here without changing
    API routes or the LLM service orchestration layer.
    """
    provider = settings.llm_provider.strip().lower()
    if provider == "ollama":
        return OllamaProvider(settings=settings, http_client=http_client)
    raise ValueError(f"Unsupported LLM provider: {provider}")
