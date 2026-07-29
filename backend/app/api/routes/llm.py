"""LLM status and generation API routes."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.requests import ClientDisconnect

from app.api.deps import CurrentActiveUser
from app.llm.schemas import GenerateRequest, GenerateResponse, LLMStatusResponse
from app.services.llm import LLMService

logger = logging.getLogger("cortexa.api.llm")

router = APIRouter(prefix="/llm", tags=["llm"])


def _llm_service(request: Request) -> LLMService:
    service = getattr(request.app.state, "llm_service", None)
    if not isinstance(service, LLMService):
        raise RuntimeError("LLM service is not configured")
    return service


@router.get(
    "/status",
    response_model=LLMStatusResponse,
    summary="LLM provider and model availability status",
)
async def llm_status(request: Request) -> LLMStatusResponse:
    """Report configured provider/model reachability without affecting /ready.

    Public by design — does not require authentication.
    """
    return await _llm_service(request).status()


@router.post(
    "/generate",
    response_model=GenerateResponse,
    summary="Non-streaming text generation",
)
async def llm_generate(
    request: Request,
    body: GenerateRequest,
    _user: CurrentActiveUser,
) -> GenerateResponse:
    return await _llm_service(request).generate(body)


@router.post(
    "/stream",
    summary="Streaming text generation (SSE)",
    response_class=StreamingResponse,
)
async def llm_stream(
    request: Request,
    body: GenerateRequest,
    _user: CurrentActiveUser,
) -> StreamingResponse:
    service = _llm_service(request)

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            async for event in service.stream(body):
                if await request.is_disconnected():
                    logger.info("llm_stream_client_disconnected")
                    break
                yield event.to_sse().encode("utf-8")
        except ClientDisconnect:
            logger.info("llm_stream_client_disconnect_exception")
        except Exception:
            # Emit a controlled SSE error when possible; never leak internals.
            logger.exception("llm_stream_unexpected_failure")
            from app.llm.schemas import StreamEvent, StreamEventType

            error_event = StreamEvent(
                event=StreamEventType.error,
                data={
                    "code": "llm_generation_error",
                    "message": "Streaming generation failed",
                },
            )
            yield error_event.to_sse().encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
