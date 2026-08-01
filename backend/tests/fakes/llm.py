"""Deterministic fake LLM provider for tests only — not a real model."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field

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
    ToolCallRequest,
)


@dataclass
class FakeLLMTurn:
    """One scripted provider response for multi-turn agent tests."""

    content: str = "fake completion"
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str | None = None
    stream_chunks: list[str] | None = None


class FakeLLMProvider:
    """Test-only LLM provider with injectable outcomes.

    This is deliberately deterministic and must never be presented as a real LLM.
    Supports scripted tool-call turns via ``scripted_turns`` or ``turn_factory``.

    Phase 9.2 multi-agent tests also script JSON content for:
    - valid / invalid / malformed agent plans
    - safety allow / block decisions
    - specialist synthesis responses
    - provider timeout / unavailable via ``fail_mode``
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
        scripted_turns: Sequence[FakeLLMTurn] | None = None,
        turn_factory: Callable[[GenerateRequest, int], FakeLLMTurn] | None = None,
        stream_delay_seconds: float = 0.0,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        self._provider_name = provider_name
        self._model = model
        self.provider_reachable = provider_reachable
        self.model_available = model_available
        self.generate_content = generate_content
        self.fail_mode = fail_mode
        self.generate_calls = 0
        self.stream_calls = 0
        self.last_request: GenerateRequest | None = None
        self.requests: list[GenerateRequest] = []
        self._scripted_turns = list(scripted_turns or [])
        self._turn_factory = turn_factory
        self.stream_delay_seconds = stream_delay_seconds
        self.cancel_event = cancel_event
        self.stream_cancelled = False
        self.generate_cancelled = False

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

    def _next_turn(self, request: GenerateRequest, *, for_stream: bool = False) -> FakeLLMTurn:
        index = (self.generate_calls + self.stream_calls) - 1
        if self._turn_factory is not None:
            return self._turn_factory(request, index)
        if index < len(self._scripted_turns):
            return self._scripted_turns[index]
        content = self.generate_content
        if for_stream and not self._scripted_turns:
            content = self.generate_content
        return FakeLLMTurn(content=content, finish_reason="stop")

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        self.generate_calls += 1
        self.last_request = request
        self.requests.append(request)
        try:
            if self.stream_delay_seconds > 0:
                await asyncio.sleep(self.stream_delay_seconds)
            self._raise_if_configured()
        except asyncio.CancelledError:
            self.generate_cancelled = True
            raise
        model = request.model or self._model
        turn = self._next_turn(request)
        finish = turn.finish_reason
        if turn.tool_calls and not finish:
            finish = "tool_calls"
        return GenerateResponse(
            provider=self.name,
            model=model,
            content=turn.content,
            finish_reason=finish or "stop",
            usage=TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
            latency_ms=1.5,
            tool_calls=list(turn.tool_calls),
        )

    async def stream(self, request: GenerateRequest) -> AsyncIterator[StreamEvent]:
        self.stream_calls += 1
        self.last_request = request
        self.requests.append(request)
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
        if self.fail_mode == "first_token_timeout":
            yield StreamEvent(
                event=StreamEventType.error,
                data={
                    "code": "llm_first_token_timeout",
                    "message": "Timed out waiting for the first model token",
                },
            )
            return
        if self.fail_mode == "timeout":
            yield StreamEvent(
                event=StreamEventType.error,
                data={
                    "code": "llm_request_timeout",
                    "message": "LLM provider request timed out",
                },
            )
            return
        if self.fail_mode:
            self._raise_if_configured()

        turn = self._next_turn(request, for_stream=True)
        if turn.stream_chunks:
            chunks = list(turn.stream_chunks)
        elif self._scripted_turns or self.generate_content != "fake completion":
            content = turn.content or self.generate_content or "Hello world"
            if " " in content:
                parts = content.split(" ")
                chunks = []
                for i, part in enumerate(parts):
                    chunks.append(part)
                    if i < len(parts) - 1:
                        chunks.append(" ")
            elif len(content) > 1:
                # Short single-token replies still emit progressive character chunks.
                mid = max(1, len(content) // 2)
                chunks = [content[:mid], content[mid:]]
            else:
                chunks = [content] if content else []
        else:
            # Backward-compatible default used by Phase 2/5 stream tests.
            chunks = ["Hello", " ", "world"]

        assembled = ""
        try:
            for token in chunks:
                if self.cancel_event is not None and self.cancel_event.is_set():
                    self.stream_cancelled = True
                    raise asyncio.CancelledError()
                if self.stream_delay_seconds > 0:
                    await asyncio.sleep(self.stream_delay_seconds)
                assembled += token
                yield StreamEvent(event=StreamEventType.delta, data={"content": token})
        except asyncio.CancelledError:
            self.stream_cancelled = True
            raise

        yield StreamEvent(
            event=StreamEventType.complete,
            data={
                "provider": self.name,
                "model": model,
                "content": assembled,
                "finish_reason": turn.finish_reason or "stop",
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
