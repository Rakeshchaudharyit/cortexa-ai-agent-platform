"""LLM application service — validation, limits, and provider orchestration."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.core.config import Settings
from app.core.logging import request_id_ctx
from app.llm.base import LLMProvider
from app.llm.exceptions import LLMModelUnavailableError
from app.llm.schemas import (
    GenerateRequest,
    GenerateResponse,
    LLMStatusResponse,
    StreamEvent,
)

logger = logging.getLogger("cortexa.llm.service")


@dataclass
class LLMService:
    """Business façade over the configured LLM provider."""

    settings: Settings
    provider: LLMProvider

    async def status(self) -> LLMStatusResponse:
        result = await self.provider.health_check()
        return LLMStatusResponse(
            provider=result.provider,
            model=result.model,
            provider_reachable=result.provider_reachable,
            model_available=result.model_available,
            status=result.status,
            message=result.message,
        )

    def _enforce_limits(self, request: GenerateRequest) -> None:
        total_chars = 0
        if request.system:
            total_chars += len(request.system)
        for message in request.messages:
            total_chars += len(message.content)
        if total_chars > self.settings.llm_max_input_characters:
            from fastapi import status

            from app.core.exceptions import AppError

            raise AppError(
                code="llm_input_too_large",
                message=(
                    "Request exceeds the configured maximum input size "
                    f"({self.settings.llm_max_input_characters} characters)"
                ),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if (
            request.max_tokens is not None
            and request.max_tokens > self.settings.llm_max_output_tokens
        ):
            from fastapi import status

            from app.core.exceptions import AppError

            raise AppError(
                code="llm_max_tokens_exceeded",
                message=(
                    "max_tokens exceeds the configured limit "
                    f"({self.settings.llm_max_output_tokens})"
                ),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        self._enforce_limits(request)
        request_id = request_id_ctx.get() or "-"
        logger.info(
            "llm_service_generate provider=%s model=%s request_id=%s",
            self.provider.name,
            request.model or self.provider.default_model,
            request_id,
        )
        return await self.provider.generate(request)

    async def stream(self, request: GenerateRequest) -> AsyncIterator[StreamEvent]:
        self._enforce_limits(request)
        request_id = request_id_ctx.get() or "-"
        logger.info(
            "llm_service_stream provider=%s model=%s request_id=%s",
            self.provider.name,
            request.model or self.provider.default_model,
            request_id,
        )
        async for event in self.provider.stream(request):
            yield event

    async def ensure_model_ready(self) -> None:
        """Optional pre-flight used by callers that want fail-fast semantics."""
        status = await self.status()
        if not status.provider_reachable:
            from app.llm.exceptions import LLMProviderUnavailableError

            raise LLMProviderUnavailableError(status.message)
        if not status.model_available:
            raise LLMModelUnavailableError(status.message)
