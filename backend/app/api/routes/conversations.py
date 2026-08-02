"""API routes for persistent conversations and multi-turn chat."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from starlette.requests import ClientDisconnect

from app.api.deps import ChatServiceDep, ConversationServiceDep, CurrentActiveUser, DbSessionDep
from app.conversations.schemas import (
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationMemoryUpdateRequest,
    ConversationSummaryResponse,
    ConversationUpdateRequest,
    CreateMessageRequest,
    CreateMessageResponse,
    EditMessageRequest,
    MessageResponse,
    RegenerateRequest,
    UsageSummaryResponse,
)
from app.core.exceptions import AppError
from app.llm.schemas import StreamEvent, StreamEventType
from app.models.enums import ConversationStatus
from app.services.conversations import conversation_to_summary, message_to_response

logger = logging.getLogger("cortexa.api.conversations")

router = APIRouter(prefix="/conversations", tags=["conversations"])
usage_router = APIRouter(prefix="/usage", tags=["usage"])


async def _client_disconnected(request: Request) -> bool:
    """Poll disconnect without blocking forever on a quiet client."""
    while True:
        if await request.is_disconnected():
            return True
        await asyncio.sleep(0.25)


async def _aclose_agen(agen: AsyncIterator[StreamEvent]) -> None:
    closer = getattr(agen, "aclose", None)
    if closer is not None:
        await closer()


@router.post(
    "",
    response_model=ConversationSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a conversation",
)
async def create_conversation(
    body: ConversationCreateRequest,
    session: DbSessionDep,
    user: CurrentActiveUser,
    conversations: ConversationServiceDep,
    chat: ChatServiceDep,
) -> ConversationSummaryResponse:
    conversation = await conversations.create_conversation(session, user, body)
    await session.commit()
    await session.refresh(conversation)

    if body.initial_message:
        result = await chat.send_message(
            session,
            user,
            conversation.id,
            CreateMessageRequest(content=body.initial_message, document_ids=body.document_ids),
        )
        return result.conversation

    return conversation_to_summary(conversation)


@router.get(
    "",
    response_model=ConversationListResponse,
    summary="List conversations",
)
async def list_conversations(
    session: DbSessionDep,
    user: CurrentActiveUser,
    conversations: ConversationServiceDep,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_archived: Annotated[bool, Query()] = False,
    status_filter: Annotated[
        ConversationStatus | None,
        Query(alias="status"),
    ] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> ConversationListResponse:
    return await conversations.list_conversations(
        session,
        user,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
        status=status_filter,
        q=q,
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Get conversation detail",
)
async def get_conversation(
    conversation_id: uuid.UUID,
    session: DbSessionDep,
    user: CurrentActiveUser,
    conversations: ConversationServiceDep,
) -> ConversationDetailResponse:
    return await conversations.get_conversation_detail(session, user, conversation_id)


@router.patch(
    "/{conversation_id}",
    response_model=ConversationSummaryResponse,
    summary="Rename a conversation",
)
async def rename_conversation(
    conversation_id: uuid.UUID,
    body: ConversationUpdateRequest,
    session: DbSessionDep,
    user: CurrentActiveUser,
    conversations: ConversationServiceDep,
) -> ConversationSummaryResponse:
    conversation = await conversations.rename_conversation(
        session,
        user,
        conversation_id,
        body.title,
    )
    await session.commit()
    await session.refresh(conversation)
    return conversation_to_summary(conversation)


@router.patch(
    "/{conversation_id}/memory",
    response_model=ConversationSummaryResponse,
    summary="Enable or disable long-term memory for this conversation",
)
async def update_conversation_memory(
    conversation_id: uuid.UUID,
    body: ConversationMemoryUpdateRequest,
    session: DbSessionDep,
    user: CurrentActiveUser,
    conversations: ConversationServiceDep,
) -> ConversationSummaryResponse:
    conversation = await conversations.set_memory_enabled(
        session,
        user,
        conversation_id,
        memory_enabled=body.memory_enabled,
        reason=body.reason,
    )
    await session.commit()
    await session.refresh(conversation)
    return conversation_to_summary(conversation)


@router.post(
    "/{conversation_id}/archive",
    response_model=ConversationSummaryResponse,
    summary="Archive a conversation",
)
async def archive_conversation(
    conversation_id: uuid.UUID,
    session: DbSessionDep,
    user: CurrentActiveUser,
    conversations: ConversationServiceDep,
) -> ConversationSummaryResponse:
    conversation = await conversations.archive_conversation(session, user, conversation_id)
    await session.commit()
    await session.refresh(conversation)
    return conversation_to_summary(conversation)


@router.post(
    "/{conversation_id}/unarchive",
    response_model=ConversationSummaryResponse,
    summary="Unarchive a conversation",
)
async def unarchive_conversation(
    conversation_id: uuid.UUID,
    session: DbSessionDep,
    user: CurrentActiveUser,
    conversations: ConversationServiceDep,
) -> ConversationSummaryResponse:
    conversation = await conversations.unarchive_conversation(session, user, conversation_id)
    await session.commit()
    await session.refresh(conversation)
    return conversation_to_summary(conversation)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation",
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    session: DbSessionDep,
    user: CurrentActiveUser,
    conversations: ConversationServiceDep,
) -> Response:
    await conversations.delete_conversation(session, user, conversation_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{conversation_id}/messages",
    response_model=CreateMessageResponse,
    summary="Send a non-streaming multi-turn chat message",
)
async def send_message(
    conversation_id: uuid.UUID,
    body: CreateMessageRequest,
    session: DbSessionDep,
    user: CurrentActiveUser,
    chat: ChatServiceDep,
) -> CreateMessageResponse:
    return await chat.send_message(session, user, conversation_id, body)


@router.post(
    "/{conversation_id}/messages/stream",
    summary="Send a streaming multi-turn chat message (SSE)",
    response_class=StreamingResponse,
)
async def stream_message(
    conversation_id: uuid.UUID,
    body: CreateMessageRequest,
    request: Request,
    session: DbSessionDep,
    user: CurrentActiveUser,
    chat: ChatServiceDep,
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[bytes]:
        agen = chat.stream_message(session, user, conversation_id, body)
        disconnect_task: asyncio.Task[bool] | None = None
        next_event_task: asyncio.Task[StreamEvent] | None = None
        try:
            disconnect_task = asyncio.create_task(
                _client_disconnected(request),
                name="conversation-stream-disconnect",
            )
            while True:
                next_event_task = asyncio.create_task(
                    agen.__anext__(),  # type: ignore[arg-type]
                    name="conversation-stream-next",
                )
                done, _pending = await asyncio.wait(
                    {next_event_task, disconnect_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if disconnect_task in done:
                    logger.info("conversation_stream_client_disconnected")
                    next_event_task.cancel()
                    try:
                        await next_event_task
                    except (asyncio.CancelledError, StopAsyncIteration):
                        pass
                    await _aclose_agen(agen)
                    break
                try:
                    event = next_event_task.result()
                except StopAsyncIteration:
                    break
                except asyncio.CancelledError:
                    break
                yield event.to_sse().encode("utf-8")
        except ClientDisconnect:
            logger.info("conversation_stream_client_disconnect_exception")
            if next_event_task is not None and not next_event_task.done():
                next_event_task.cancel()
            await _aclose_agen(agen)
        except AppError as exc:
            error_event = StreamEvent(
                event=StreamEventType.error,
                data={"error": {"code": exc.code, "message": exc.message}},
            )
            yield error_event.to_sse().encode("utf-8")
        except Exception:
            logger.exception("conversation_stream_unexpected_failure")
            error_event = StreamEvent(
                event=StreamEventType.error,
                data={
                    "error": {
                        "code": "conversation_stream_error",
                        "message": "Streaming generation failed",
                    }
                },
            )
            yield error_event.to_sse().encode("utf-8")
        finally:
            if disconnect_task is not None and not disconnect_task.done():
                disconnect_task.cancel()
                try:
                    await disconnect_task
                except asyncio.CancelledError:
                    pass
            # Streaming responses can finish because the client disconnect
            # watcher wins immediately after the final event. Close the service
            # generator and end any read transaction it opened while serializing
            # the final message before the request-scoped session is released.
            try:
                await _aclose_agen(agen)
            finally:
                await session.rollback()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.patch(
    "/{conversation_id}/messages/{message_id}",
    response_model=MessageResponse,
    summary="Edit the latest user message",
)
async def edit_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    body: EditMessageRequest,
    session: DbSessionDep,
    user: CurrentActiveUser,
    conversations: ConversationServiceDep,
    chat: ChatServiceDep,
) -> MessageResponse:
    conversation = await conversations.require_active_conversation(
        session,
        user,
        conversation_id,
        for_update=True,
    )
    replacement = await chat.message_service.edit_latest_user_message(
        session,
        user,
        conversation,
        message_id,
        body.content,
    )
    await session.commit()
    await session.refresh(replacement)
    return message_to_response(replacement)


@router.post(
    "/{conversation_id}/regenerate",
    response_model=CreateMessageResponse,
    summary="Regenerate the latest assistant answer",
)
async def regenerate_message(
    conversation_id: uuid.UUID,
    body: RegenerateRequest,
    session: DbSessionDep,
    user: CurrentActiveUser,
    chat: ChatServiceDep,
) -> CreateMessageResponse:
    return await chat.regenerate(session, user, conversation_id, body)


@usage_router.get(
    "/summary",
    response_model=UsageSummaryResponse,
    summary="Authenticated usage summary",
)
async def usage_summary(
    session: DbSessionDep,
    user: CurrentActiveUser,
    chat: ChatServiceDep,
) -> UsageSummaryResponse:
    return await chat.usage_summary(session, user)
