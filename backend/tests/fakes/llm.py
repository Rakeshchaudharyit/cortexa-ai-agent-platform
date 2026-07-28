"""Deterministic fake LLM provider for tests only — not a real model."""

from __future__ import annotations

from collections.abc import AsyncIterator

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
    ProviderHealthResult,
    StreamEvent,
    StreamEventType,
    TokenUsage,
)


class FakeLLMProvider:
    """Test-only LLM provider with injectable outcomes.

    This is deliberately deterministic and must never be presented as a real LLM.
    """

    def __init__(
        self,
        *,
        provider_name: str = "fake",
        model: str = "fake-model",
        provider_reachable: bool = True,
        model_available: bool = True,
        generate_content: str = "fake completion",
        fail_mode: str | None = None,
    ) -> None:
        self._provider_name = provider_name
        self._model = model
        self.provider_reachable = provider_reachable
        self.model_available = model_available
        self.generate_content = generate_content
        self.fail_mode = fail_mode
        self.generate_calls = 0
        self.stream_calls = 0

    @property
    def name(self) -> str:
        return self._provider_name

    @property
    def default_model(self) -> str:
        return self._model

    async def health_check(self) -> ProviderHealthResult:
        if not self.provider_reachable:
            return ProviderHealthResult(
                provider=self.name,
                model=self._model,
                provider_reachable=False,
                model_available=False,
                status=LLMStatus.provider_unavailable,
                message="Fake provider is unreachable",
            )
        if not self.model_available:
            return ProviderHealthResult(
                provider=self.name,
                model=self._model,
                provider_reachable=True,
                model_available=False,
                status=LLMStatus.model_unavailable,
                message="Fake model is not available",
            )
        return ProviderHealthResult(
            provider=self.name,
            model=self._model,
            provider_reachable=True,
            model_available=True,
            status=LLMStatus.ready,
            message="Fake provider is ready",
        )

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.generate_calls += 1
        self._raise_if_configured()
        model = request.model or self._model
        return GenerateResponse(
            provider=self.name,
            model=model,
            content=self.generate_content,
            finish_reason="stop",
            usage=TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
            latency_ms=1.5,
        )

    async def stream(self, request: GenerateRequest) -> AsyncIterator[StreamEvent]:
        self.stream_calls += 1
        model = request.model or self._model
        yield StreamEvent(
            event=StreamEventType.start,
            data={"provider": self.name, "model": model},
        )
        if self.fail_mode == "stream_error":
            yield StreamEvent(
                event=StreamEventType.error,
                data={
                    "code": "llm_generation_error",
                    "message": "Fake upstream stream error",
                },
            )
            return
        if self.fail_mode:
            self._raise_if_configured()
        for token in ("Hello", " ", "world"):
            yield StreamEvent(event=StreamEventType.delta, data={"content": token})
        yield StreamEvent(
            event=StreamEventType.complete,
            data={
                "provider": self.name,
                "model": model,
                "content": "Hello world",
                "finish_reason": "stop",
                "latency_ms": 2.0,
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            },
        )

    def _raise_if_configured(self) -> None:
        if self.fail_mode == "unavailable":
            raise LLMProviderUnavailableError("Fake provider is unavailable")
        if self.fail_mode == "model_missing":
            raise LLMModelUnavailableError("Fake model is not available")
        if self.fail_mode == "timeout":
            raise LLMRequestTimeoutError("Fake provider timed out")
        if self.fail_mode == "invalid":
            raise LLMInvalidResponseError("Fake invalid response")
        if self.fail_mode == "generation":
            raise LLMGenerationError("Fake generation failed")
