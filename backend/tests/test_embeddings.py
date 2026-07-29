"""Embedding factory, fake provider, and Ollama provider unit tests."""

from __future__ import annotations

import json

import httpx
import pytest
from app.core.config import Settings
from app.embeddings.exceptions import (
    EmbeddingDimensionMismatchError,
    EmbeddingInvalidResponseError,
    EmbeddingModelUnavailableError,
    EmbeddingProviderUnavailableError,
    EmbeddingTimeoutError,
)
from app.embeddings.factory import create_embedding_provider
from app.embeddings.providers.ollama import OllamaEmbeddingProvider
from app.embeddings.schemas import EmbeddingStatus
from app.services.embeddings import EmbeddingService

from tests.fakes.embeddings import FakeEmbeddingProvider


def test_factory_creates_ollama(settings: Settings) -> None:
    client = httpx.AsyncClient()
    provider = create_embedding_provider(settings, client)
    assert isinstance(provider, OllamaEmbeddingProvider)
    assert provider.name == "ollama"
    assert provider.model == "nomic-embed-text"
    assert provider.dimension == 768


def test_factory_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    from app.core.config import clear_settings_cache
    from pydantic import ValidationError

    clear_settings_cache()
    with pytest.raises(ValidationError):
        Settings()
    clear_settings_cache()


@pytest.mark.asyncio
async def test_fake_embedding_modes(settings: Settings) -> None:
    ready = FakeEmbeddingProvider(dimension=settings.embedding_dimension)
    health = await ready.health_check()
    assert health.status == EmbeddingStatus.ready
    vector = await ready.embed("hello")
    assert len(vector) == settings.embedding_dimension
    assert any(value != 0.0 for value in vector)

    identical = FakeEmbeddingProvider(dimension=8, identical_vectors=True)
    a = await identical.embed("one")
    b = await identical.embed("two")
    assert a == b

    for mode, exc in (
        ("unavailable", EmbeddingProviderUnavailableError),
        ("model_missing", EmbeddingModelUnavailableError),
        ("timeout", EmbeddingTimeoutError),
        ("invalid", EmbeddingInvalidResponseError),
        ("dimension_mismatch", EmbeddingDimensionMismatchError),
    ):
        provider = FakeEmbeddingProvider(dimension=8, fail_mode=mode)
        with pytest.raises(exc):
            await provider.embed("x")


@pytest.mark.asyncio
async def test_fake_wrong_batch_count() -> None:
    provider = FakeEmbeddingProvider(dimension=4, fail_mode="wrong_batch_count")
    batch = await provider.embed_batch(["a", "b", "c"])
    assert len(batch) == 1


@pytest.mark.asyncio
async def test_embedding_service_status(settings: Settings) -> None:
    provider = FakeEmbeddingProvider(
        model=settings.ollama_embedding_model,
        dimension=settings.embedding_dimension,
    )
    service = EmbeddingService(settings=settings, provider=provider)
    status = await service.status()
    assert status.provider == "fake"
    assert status.model_available is True
    assert status.configured_dimension == 768


def _ollama_provider(settings: Settings, handler: httpx.MockTransport) -> OllamaEmbeddingProvider:
    client = httpx.AsyncClient(transport=handler, base_url="http://ollama:11434")
    return OllamaEmbeddingProvider(settings=settings, http_client=client)


@pytest.mark.asyncio
async def test_ollama_embedding_health_ready(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={"models": [{"name": "nomic-embed-text"}, {"name": "qwen2.5:7b"}]},
        )

    provider = _ollama_provider(settings, httpx.MockTransport(handler))
    result = await provider.health_check()
    assert result.status == EmbeddingStatus.ready
    assert result.model_available is True
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_embedding_health_model_missing(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}]})

    provider = _ollama_provider(settings, httpx.MockTransport(handler))
    result = await provider.health_check()
    assert result.status == EmbeddingStatus.model_unavailable
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_embed_success(settings: Settings) -> None:
    vector = [0.1] * settings.embedding_dimension
    vector[0] = 0.5

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "nomic-embed-text"
        return httpx.Response(200, json={"embeddings": [vector]})

    provider = _ollama_provider(settings, httpx.MockTransport(handler))
    result = await provider.embed("hello cortexa")
    assert len(result) == settings.embedding_dimension
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_embed_dimension_mismatch(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})

    provider = _ollama_provider(settings, httpx.MockTransport(handler))
    with pytest.raises(EmbeddingDimensionMismatchError):
        await provider.embed("hello")
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_embed_timeout(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = _ollama_provider(settings, httpx.MockTransport(handler))
    with pytest.raises(EmbeddingTimeoutError):
        await provider.embed("hello")
    await provider._http.aclose()
