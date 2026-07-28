"""LLM settings, factory, validation, and API tests."""

from __future__ import annotations

import httpx
import pytest
from app.core.config import Settings, clear_settings_cache
from app.llm.factory import create_llm_provider
from app.llm.providers.ollama import OllamaProvider
from app.llm.schemas import GenerateRequest, MessageRole
from app.main import create_app
from app.services.llm import LLMService
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from tests.conftest import StubHealthService
from tests.fakes.llm import FakeLLMProvider


def test_llm_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_cache()
    for key in (
        "LLM_PROVIDER",
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
        "OLLAMA_REQUEST_TIMEOUT_SECONDS",
        "OLLAMA_CONNECT_TIMEOUT_SECONDS",
        "LLM_MAX_INPUT_CHARACTERS",
        "LLM_MAX_OUTPUT_TOKENS",
        "LLM_DEFAULT_TEMPERATURE",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = Settings()
    assert settings.llm_provider == "ollama"
    assert settings.ollama_base_url == "http://ollama:11434"
    assert settings.ollama_model == "qwen2.5:7b"
    assert settings.ollama_request_timeout_seconds == 120.0
    assert settings.ollama_connect_timeout_seconds == 5.0
    assert settings.llm_max_input_characters == 32_000
    assert settings.llm_max_output_tokens == 2048
    assert settings.llm_default_temperature == 0.7
    clear_settings_cache()


def test_llm_settings_validation_rejects_bad_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(ValidationError):
        Settings()


def test_llm_settings_validation_rejects_bad_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "ollama:11434")
    with pytest.raises(ValidationError):
        Settings()


def test_safe_dict_omits_ollama_base_url(settings: Settings) -> None:
    safe = settings.safe_dict()
    assert "ollama_base_url" not in safe
    assert safe["llm_provider"] == "ollama"
    assert safe["ollama_model"] == "qwen2.5:7b"


def test_factory_resolves_ollama(settings: Settings) -> None:
    client = httpx.AsyncClient()
    provider = create_llm_provider(settings, client)
    assert isinstance(provider, OllamaProvider)
    assert provider.name == "ollama"
    assert provider.default_model == "qwen2.5:7b"


def test_generate_request_validation_rejects_blank_message() -> None:
    with pytest.raises(ValidationError):
        GenerateRequest(messages=[{"role": "user", "content": "   "}])


def test_generate_request_validation_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        GenerateRequest(messages=[{"role": "tool", "content": "hi"}])


def test_generate_request_validation_rejects_bad_temperature() -> None:
    with pytest.raises(ValidationError):
        GenerateRequest(
            messages=[{"role": MessageRole.user, "content": "hi"}],
            temperature=2.5,
        )


@pytest.mark.asyncio
async def test_status_ready_with_fake(client: AsyncClient) -> None:
    response = await client.get("/api/v1/llm/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "fake"
    assert payload["model"] == "qwen2.5:7b"
    assert payload["provider_reachable"] is True
    assert payload["model_available"] is True
    assert payload["status"] == "ready"


@pytest.mark.asyncio
async def test_status_provider_unavailable(settings: Settings) -> None:
    app = create_app(settings)
    app.state.health_service = StubHealthService(settings)
    app.state.llm_service = LLMService(
        settings=settings,
        provider=FakeLLMProvider(provider_reachable=False, model="qwen2.5:7b"),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/llm/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_reachable"] is False
    assert payload["model_available"] is False
    assert payload["status"] == "provider_unavailable"


@pytest.mark.asyncio
async def test_status_model_unavailable(settings: Settings) -> None:
    app = create_app(settings)
    app.state.health_service = StubHealthService(settings)
    app.state.llm_service = LLMService(
        settings=settings,
        provider=FakeLLMProvider(
            provider_reachable=True,
            model_available=False,
            model="qwen2.5:7b",
        ),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/llm/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_reachable"] is True
    assert payload["model_available"] is False
    assert payload["status"] == "model_unavailable"


@pytest.mark.asyncio
async def test_generate_success(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/llm/generate",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "fake"
    assert payload["model"] == "qwen2.5:7b"
    assert payload["content"] == "fake completion"
    assert payload["usage"]["total_tokens"] == 5
    assert "traceback" not in response.text.lower()


@pytest.mark.asyncio
async def test_generate_provider_timeout_maps_to_504(settings: Settings) -> None:
    app = create_app(settings)
    app.state.health_service = StubHealthService(settings)
    app.state.llm_service = LLMService(
        settings=settings,
        provider=FakeLLMProvider(fail_mode="timeout", model="qwen2.5:7b"),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/llm/generate",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
    assert response.status_code == 504
    payload = response.json()
    assert payload["error"]["code"] == "llm_request_timeout"
    assert "traceback" not in response.text.lower()


@pytest.mark.asyncio
async def test_generate_model_unavailable_maps_to_424(settings: Settings) -> None:
    app = create_app(settings)
    app.state.health_service = StubHealthService(settings)
    app.state.llm_service = LLMService(
        settings=settings,
        provider=FakeLLMProvider(fail_mode="model_missing", model="qwen2.5:7b"),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/llm/generate",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
    assert response.status_code == 424
    assert response.json()["error"]["code"] == "llm_model_unavailable"


@pytest.mark.asyncio
async def test_generate_provider_unavailable_maps_to_503(settings: Settings) -> None:
    app = create_app(settings)
    app.state.health_service = StubHealthService(settings)
    app.state.llm_service = LLMService(
        settings=settings,
        provider=FakeLLMProvider(fail_mode="unavailable", model="qwen2.5:7b"),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/llm/generate",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_provider_unavailable"


@pytest.mark.asyncio
async def test_generate_invalid_upstream_maps_to_502(settings: Settings) -> None:
    app = create_app(settings)
    app.state.health_service = StubHealthService(settings)
    app.state.llm_service = LLMService(
        settings=settings,
        provider=FakeLLMProvider(fail_mode="invalid", model="qwen2.5:7b"),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/llm/generate",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "llm_invalid_response"


@pytest.mark.asyncio
async def test_generate_rejects_oversized_input(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/llm/generate",
        json={"messages": [{"role": "user", "content": "x" * 1001}]},
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "llm_input_too_large"


@pytest.mark.asyncio
async def test_generate_rejects_max_tokens_over_limit(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/llm/generate",
        json={
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 500,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "llm_max_tokens_exceeded"


@pytest.mark.asyncio
async def test_generate_request_validation_empty_messages(client: AsyncClient) -> None:
    response = await client.post("/api/v1/llm/generate", json={"messages": []})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_stream_events(client: AsyncClient) -> None:
    async with client.stream(
        "POST",
        "/api/v1/llm/stream",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = (await response.aread()).decode("utf-8")

    assert "event: start" in body
    assert "event: delta" in body
    assert "event: complete" in body
    assert "Hello world" in body
    assert "raw_ollama" not in body
    assert "traceback" not in body.lower()


@pytest.mark.asyncio
async def test_stream_upstream_error_event(settings: Settings) -> None:
    app = create_app(settings)
    app.state.health_service = StubHealthService(settings)
    app.state.llm_service = LLMService(
        settings=settings,
        provider=FakeLLMProvider(fail_mode="stream_error", model="qwen2.5:7b"),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/api/v1/llm/stream",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        ) as response:
            body = (await response.aread()).decode("utf-8")
    assert "event: start" in body
    assert "event: error" in body
    assert "llm_generation_error" in body
