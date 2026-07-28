"""Ollama provider tests using mocked HTTP transports."""

from __future__ import annotations

import json

import httpx
import pytest
from app.core.config import Settings
from app.llm.exceptions import (
    LLMInvalidResponseError,
    LLMModelUnavailableError,
    LLMProviderUnavailableError,
    LLMRequestTimeoutError,
)
from app.llm.providers.ollama import OllamaProvider
from app.llm.schemas import GenerateRequest, LLMStatus, MessageRole


def _provider(settings: Settings, handler: httpx.MockTransport) -> OllamaProvider:
    client = httpx.AsyncClient(transport=handler, base_url="http://ollama:11434")
    return OllamaProvider(settings=settings, http_client=client)


@pytest.mark.asyncio
async def test_ollama_status_reachable_model_present(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={"models": [{"name": "qwen2.5:7b"}, {"name": "llama3.1:8b"}]},
        )

    provider = _provider(settings, httpx.MockTransport(handler))
    result = await provider.health_check()
    assert result.provider_reachable is True
    assert result.model_available is True
    assert result.status == LLMStatus.ready
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_status_reachable_model_missing(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "llama3.1:8b"}]})

    provider = _provider(settings, httpx.MockTransport(handler))
    result = await provider.health_check()
    assert result.provider_reachable is True
    assert result.model_available is False
    assert result.status == LLMStatus.model_unavailable
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_status_unavailable(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = _provider(settings, httpx.MockTransport(handler))
    result = await provider.health_check()
    assert result.provider_reachable is False
    assert result.model_available is False
    assert result.status == LLMStatus.provider_unavailable
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_generate_success(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = json.loads(request.content.decode("utf-8"))
        assert body["stream"] is False
        assert body["model"] == "qwen2.5:7b"
        assert body["messages"][0]["role"] == "user"
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5:7b",
                "message": {"role": "assistant", "content": "pong"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 4,
                "eval_count": 1,
            },
        )

    provider = _provider(settings, httpx.MockTransport(handler))
    response = await provider.generate(
        GenerateRequest(messages=[{"role": MessageRole.user, "content": "ping"}]),
    )
    assert response.content == "pong"
    assert response.provider == "ollama"
    assert response.usage is not None
    assert response.usage.total_tokens == 5
    assert response.finish_reason == "stop"
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_generate_timeout(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = _provider(settings, httpx.MockTransport(handler))
    with pytest.raises(LLMRequestTimeoutError):
        await provider.generate(
            GenerateRequest(messages=[{"role": MessageRole.user, "content": "ping"}]),
        )
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_generate_malformed_response(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"role": "assistant"}})

    provider = _provider(settings, httpx.MockTransport(handler))
    with pytest.raises(LLMInvalidResponseError):
        await provider.generate(
            GenerateRequest(messages=[{"role": MessageRole.user, "content": "ping"}]),
        )
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_generate_model_missing(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    provider = _provider(settings, httpx.MockTransport(handler))
    with pytest.raises(LLMModelUnavailableError):
        await provider.generate(
            GenerateRequest(messages=[{"role": MessageRole.user, "content": "ping"}]),
        )
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_generate_unreachable(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    provider = _provider(settings, httpx.MockTransport(handler))
    with pytest.raises(LLMProviderUnavailableError):
        await provider.generate(
            GenerateRequest(messages=[{"role": MessageRole.user, "content": "ping"}]),
        )
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_stream_events(settings: Settings) -> None:
    chunks = [
        {"model": "qwen2.5:7b", "message": {"role": "assistant", "content": "Hel"}, "done": False},
        {"model": "qwen2.5:7b", "message": {"role": "assistant", "content": "lo"}, "done": False},
        {
            "model": "qwen2.5:7b",
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 2,
            "eval_count": 2,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        payload = "\n".join(json.dumps(chunk) for chunk in chunks)
        return httpx.Response(200, content=payload.encode("utf-8"))

    provider = _provider(settings, httpx.MockTransport(handler))
    events = [
        event
        async for event in provider.stream(
            GenerateRequest(messages=[{"role": MessageRole.user, "content": "hi"}]),
        )
    ]
    assert events[0].event.value == "start"
    assert events[1].event.value == "delta"
    assert events[1].data["content"] == "Hel"
    assert events[2].event.value == "delta"
    assert events[2].data["content"] == "lo"
    assert events[3].event.value == "complete"
    assert events[3].data["content"] == "Hello"
    assert events[3].data["usage"]["total_tokens"] == 4
    # No raw upstream leakage keys.
    serialized = json.dumps([e.model_dump() for e in events])
    assert "prompt_eval_count" not in serialized
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_stream_malformed_chunk(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json\n")

    provider = _provider(settings, httpx.MockTransport(handler))
    events = [
        event
        async for event in provider.stream(
            GenerateRequest(messages=[{"role": MessageRole.user, "content": "hi"}]),
        )
    ]
    assert events[0].event.value == "start"
    assert events[1].event.value == "error"
    assert events[1].data["code"] == "llm_invalid_response"
    await provider._http.aclose()


@pytest.mark.asyncio
async def test_ollama_does_not_fabricate_usage(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5:7b",
                "message": {"role": "assistant", "content": "ok"},
                "done": True,
            },
        )

    provider = _provider(settings, httpx.MockTransport(handler))
    response = await provider.generate(
        GenerateRequest(messages=[{"role": MessageRole.user, "content": "ping"}]),
    )
    assert response.usage is None
    await provider._http.aclose()
