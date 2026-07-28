"""Ollama HTTP LLM provider."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Mapping
from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import request_id_ctx
from app.llm.exceptions import (
    LLMGenerationError,
    LLMInvalidResponseError,
    LLMModelUnavailableError,
    LLMProviderUnavailableError,
    LLMRequestTimeoutError,
)
from app.llm.schemas import (
    GenerateRequest,
    GenerateResponse,
    LLMStatus,
    MessageRole,
    ProviderHealthResult,
    StreamEvent,
    StreamEventType,
    TokenUsage,
)

logger = logging.getLogger("cortexa.llm.ollama")


def _model_matches(installed: str, requested: str) -> bool:
    """Match Ollama model names allowing optional digest suffixes."""
    left = installed.strip().lower()
    right = requested.strip().lower()
    if left == right:
        return True
    # Tags may appear as name:tag or name:tag@digest
    left_base = left.split("@", 1)[0]
    right_base = right.split("@", 1)[0]
    return left_base == right_base


class OllamaProvider:
    """Encapsulates Ollama `/api/tags` and `/api/chat` transport details."""

    def __init__(self, *, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._base_url = settings.ollama_base_url.rstrip("/")

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def default_model(self) -> str:
        return self._settings.ollama_model

    def _resolve_model(self, request: GenerateRequest) -> str:
        return (request.model or self._settings.ollama_model).strip()

    def _build_messages(self, request: GenerateRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": MessageRole.system.value, "content": request.system})
        for message in request.messages:
            messages.append({"role": message.role.value, "content": message.content})
        return messages

    def _options(self, request: GenerateRequest) -> dict[str, Any]:
        temperature = (
            self._settings.llm_default_temperature
            if request.temperature is None
            else request.temperature
        )
        max_tokens = (
            self._settings.llm_max_output_tokens
            if request.max_tokens is None
            else min(request.max_tokens, self._settings.llm_max_output_tokens)
        )
        options: dict[str, Any] = {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
        if request.stop:
            options["stop"] = request.stop
        return options

    async def health_check(self) -> ProviderHealthResult:
        model = self._settings.ollama_model
        request_id = request_id_ctx.get() or "-"
        logger.info(
            "llm_status_check_start provider=%s model=%s request_id=%s",
            self.name,
            model,
            request_id,
        )
        try:
            response = await self._http.get(f"{self._base_url}/api/tags")
        except httpx.TimeoutException:
            logger.warning(
                "llm_status_check_timeout provider=%s model=%s request_id=%s",
                self.name,
                model,
                request_id,
            )
            return ProviderHealthResult(
                provider=self.name,
                model=model,
                provider_reachable=False,
                model_available=False,
                status=LLMStatus.provider_unavailable,
                message="Ollama did not respond before the configured timeout",
            )
        except httpx.HTTPError:
            logger.warning(
                "llm_status_check_unreachable provider=%s model=%s request_id=%s",
                self.name,
                model,
                request_id,
            )
            return ProviderHealthResult(
                provider=self.name,
                model=model,
                provider_reachable=False,
                model_available=False,
                status=LLMStatus.provider_unavailable,
                message="Ollama provider is unreachable",
            )

        if response.status_code >= 500:
            return ProviderHealthResult(
                provider=self.name,
                model=model,
                provider_reachable=False,
                model_available=False,
                status=LLMStatus.provider_unavailable,
                message="Ollama provider is unavailable",
            )
        if response.status_code >= 400:
            return ProviderHealthResult(
                provider=self.name,
                model=model,
                provider_reachable=False,
                model_available=False,
                status=LLMStatus.provider_unavailable,
                message="Ollama provider rejected the status request",
            )

        try:
            payload = response.json()
        except ValueError:
            return ProviderHealthResult(
                provider=self.name,
                model=model,
                provider_reachable=False,
                model_available=False,
                status=LLMStatus.provider_unavailable,
                message="Ollama returned an invalid status payload",
            )

        models = payload.get("models") if isinstance(payload, Mapping) else None
        if not isinstance(models, list):
            return ProviderHealthResult(
                provider=self.name,
                model=model,
                provider_reachable=False,
                model_available=False,
                status=LLMStatus.provider_unavailable,
                message="Ollama returned an invalid model inventory",
            )

        available = False
        for entry in models:
            if not isinstance(entry, Mapping):
                continue
            name = entry.get("name") or entry.get("model")
            if isinstance(name, str) and _model_matches(name, model):
                available = True
                break

        if available:
            result = ProviderHealthResult(
                provider=self.name,
                model=model,
                provider_reachable=True,
                model_available=True,
                status=LLMStatus.ready,
                message="Ollama is reachable and the configured model is available",
            )
        else:
            result = ProviderHealthResult(
                provider=self.name,
                model=model,
                provider_reachable=True,
                model_available=False,
                status=LLMStatus.model_unavailable,
                message=(
                    "Ollama is reachable but the configured model is not installed. "
                    "Pull it manually before generating."
                ),
            )
        logger.info(
            "llm_status_check_complete provider=%s model=%s status=%s request_id=%s",
            self.name,
            model,
            result.status.value,
            request_id,
        )
        return result

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        model = self._resolve_model(request)
        request_id = request_id_ctx.get() or "-"
        started = time.perf_counter()
        logger.info(
            "llm_generate_start provider=%s model=%s request_id=%s",
            self.name,
            model,
            request_id,
        )

        body: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(request),
            "stream": False,
            "options": self._options(request),
        }

        try:
            response = await self._http.post(f"{self._base_url}/api/chat", json=body)
        except httpx.TimeoutException as exc:
            logger.warning(
                "llm_generate_timeout provider=%s model=%s request_id=%s",
                self.name,
                model,
                request_id,
            )
            raise LLMRequestTimeoutError from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "llm_generate_unreachable provider=%s model=%s request_id=%s",
                self.name,
                model,
                request_id,
            )
            raise LLMProviderUnavailableError from exc

        if response.status_code == 404:
            raise LLMModelUnavailableError(
                "Requested model is not available on the Ollama provider",
            )
        if response.status_code >= 500:
            raise LLMProviderUnavailableError("Ollama provider is unavailable")
        if response.status_code >= 400:
            raise LLMGenerationError("Ollama rejected the generation request")

        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMInvalidResponseError from exc

        if not isinstance(payload, Mapping):
            raise LLMInvalidResponseError

        message = payload.get("message")
        if not isinstance(message, Mapping):
            raise LLMInvalidResponseError("Ollama response missing message content")
        content = message.get("content")
        if not isinstance(content, str):
            raise LLMInvalidResponseError("Ollama response missing message content")

        usage = self._extract_usage(payload)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        finish_reason = payload.get("done_reason")
        if finish_reason is not None and not isinstance(finish_reason, str):
            finish_reason = None

        logger.info(
            "llm_generate_success provider=%s model=%s latency_ms=%s request_id=%s",
            self.name,
            model,
            latency_ms,
            request_id,
        )
        return GenerateResponse(
            provider=self.name,
            model=str(payload.get("model") or model),
            content=content,
            finish_reason=finish_reason,
            usage=usage,
            latency_ms=latency_ms,
        )

    async def stream(self, request: GenerateRequest) -> AsyncIterator[StreamEvent]:
        model = self._resolve_model(request)
        request_id = request_id_ctx.get() or "-"
        started = time.perf_counter()
        logger.info(
            "llm_stream_start provider=%s model=%s request_id=%s",
            self.name,
            model,
            request_id,
        )

        yield StreamEvent(
            event=StreamEventType.start,
            data={"provider": self.name, "model": model},
        )

        body: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(request),
            "stream": True,
            "options": self._options(request),
        }

        try:
            async with self._http.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=body,
            ) as response:
                if response.status_code == 404:
                    yield StreamEvent(
                        event=StreamEventType.error,
                        data={
                            "code": "llm_model_unavailable",
                            "message": "Requested model is not available on the Ollama provider",
                        },
                    )
                    return
                if response.status_code >= 400:
                    code = (
                        "llm_provider_unavailable"
                        if response.status_code >= 500
                        else "llm_generation_error"
                    )
                    error_message = (
                        "Ollama provider is unavailable"
                        if response.status_code >= 500
                        else "Ollama rejected the generation request"
                    )
                    yield StreamEvent(
                        event=StreamEventType.error,
                        data={"code": code, "message": error_message},
                    )
                    return

                assembled = ""
                usage: TokenUsage | None = None
                finish_reason: str | None = None
                resolved_model = model

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning(
                            "llm_stream_malformed_chunk provider=%s model=%s request_id=%s",
                            self.name,
                            model,
                            request_id,
                        )
                        yield StreamEvent(
                            event=StreamEventType.error,
                            data={
                                "code": "llm_invalid_response",
                                "message": "Ollama returned malformed streaming data",
                            },
                        )
                        return

                    if not isinstance(chunk, Mapping):
                        yield StreamEvent(
                            event=StreamEventType.error,
                            data={
                                "code": "llm_invalid_response",
                                "message": "Ollama returned an invalid streaming payload",
                            },
                        )
                        return

                    if isinstance(chunk.get("error"), str):
                        yield StreamEvent(
                            event=StreamEventType.error,
                            data={
                                "code": "llm_generation_error",
                                "message": "Ollama reported a generation error",
                            },
                        )
                        return

                    chunk_message = chunk.get("message")
                    if isinstance(chunk_message, Mapping):
                        delta = chunk_message.get("content")
                        if isinstance(delta, str) and delta:
                            assembled += delta
                            yield StreamEvent(
                                event=StreamEventType.delta,
                                data={"content": delta},
                            )

                    if chunk.get("done") is True:
                        usage = self._extract_usage(chunk)
                        reason = chunk.get("done_reason")
                        finish_reason = reason if isinstance(reason, str) else None
                        model_name = chunk.get("model")
                        if isinstance(model_name, str) and model_name:
                            resolved_model = model_name
                        break

                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                complete_data: dict[str, Any] = {
                    "provider": self.name,
                    "model": resolved_model,
                    "content": assembled,
                    "finish_reason": finish_reason,
                    "latency_ms": latency_ms,
                }
                if usage is not None:
                    complete_data["usage"] = usage.model_dump()
                logger.info(
                    "llm_stream_complete provider=%s model=%s latency_ms=%s request_id=%s",
                    self.name,
                    resolved_model,
                    latency_ms,
                    request_id,
                )
                yield StreamEvent(event=StreamEventType.complete, data=complete_data)
        except httpx.TimeoutException:
            logger.warning(
                "llm_stream_timeout provider=%s model=%s request_id=%s",
                self.name,
                model,
                request_id,
            )
            yield StreamEvent(
                event=StreamEventType.error,
                data={
                    "code": "llm_request_timeout",
                    "message": "LLM provider request timed out",
                },
            )
        except httpx.HTTPError:
            logger.warning(
                "llm_stream_unreachable provider=%s model=%s request_id=%s",
                self.name,
                model,
                request_id,
            )
            yield StreamEvent(
                event=StreamEventType.error,
                data={
                    "code": "llm_provider_unavailable",
                    "message": "Ollama provider is unreachable",
                },
            )

    @staticmethod
    def _extract_usage(payload: Mapping[str, Any]) -> TokenUsage | None:
        prompt = payload.get("prompt_eval_count")
        completion = payload.get("eval_count")
        prompt_tokens = prompt if isinstance(prompt, int) else None
        completion_tokens = completion if isinstance(completion, int) else None
        if prompt_tokens is None and completion_tokens is None:
            return None
        total: int | None = None
        if prompt_tokens is not None and completion_tokens is not None:
            total = prompt_tokens + completion_tokens
        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
        )
