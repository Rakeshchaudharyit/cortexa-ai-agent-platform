"""Abstract LLM provider interface."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from app.llm.schemas import GenerateRequest, GenerateResponse, ProviderHealthResult, StreamEvent


@runtime_checkable
class LLMProvider(Protocol):
    """Provider-neutral LLM interface.

    Implementations must never return raw upstream transport payloads from
    application services or API routes.
    """

    @property
    def name(self) -> str:
        """Stable provider identifier (for example ``ollama``)."""

    @property
    def default_model(self) -> str:
        """Configured default model name."""

    async def health_check(self) -> ProviderHealthResult:
        """Report provider reachability and configured-model availability."""

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Run a non-streaming generation and return a normalized response."""

    def stream(self, request: GenerateRequest) -> AsyncIterator[StreamEvent]:
        """Yield normalized stream events (start, delta, complete, error)."""
