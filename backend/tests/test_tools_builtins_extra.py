"""Conversation summary and knowledge search tool unit/integration tests."""

from __future__ import annotations

import uuid

import pytest
from app.models.conversation import Conversation, Message
from app.models.enums import ConversationStatus, MessageRole, MessageStatus, UserRole, UserStatus
from app.models.user import User
from app.services.llm import LLMService
from app.tools.builtins.conversation_summary import (
    ConversationSummaryInput,
    ConversationSummaryTool,
)
from app.tools.builtins.knowledge_search import KnowledgeSearchInput, KnowledgeSearchTool
from app.tools.context import ToolExecutionContext
from app.tools.exceptions import ToolPermissionDeniedError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes.llm import FakeLLMProvider


async def _user(session: AsyncSession, *, email: str | None = None) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email or f"sum-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Summary User",
        password_hash="not-a-real-hash",
        role=UserRole.user,
        status=UserStatus.active,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_conversation_summary_owner_empty_and_limit(
    settings,
    db_session: AsyncSession,
) -> None:
    owner = await _user(db_session)
    conversation = Conversation(
        id=uuid.uuid4(),
        user_id=owner.id,
        title="Empty",
        status=ConversationStatus.active,
    )
    db_session.add(conversation)
    await db_session.flush()

    provider = FakeLLMProvider(generate_content="Summary text")
    llm = LLMService(settings=settings, provider=provider)
    tool = ConversationSummaryTool()
    ctx = ToolExecutionContext(
        session=db_session,
        user_id=owner.id,
        user_role=UserRole.user,
        llm_service=llm,
        active_tool_stack=["conversation_summary"],
    )
    empty = await tool.execute(
        ConversationSummaryInput(conversation_id=conversation.id, max_messages=10),
        ctx,
    )
    assert empty.success
    assert empty.data["empty"] is True

    for index in range(3):
        db_session.add(
            Message(
                id=uuid.uuid4(),
                conversation_id=conversation.id,
                user_id=owner.id,
                role=MessageRole.user if index % 2 == 0 else MessageRole.assistant,
                content=f"Message {index}",
                status=MessageStatus.complete,
                sequence_number=index + 1,
            )
        )
    await db_session.flush()

    filled = await tool.execute(
        ConversationSummaryInput(conversation_id=conversation.id, max_messages=2),
        ctx,
    )
    assert filled.success
    assert filled.data["message_count"] == 2
    assert filled.data["summary"] == "Summary text"


@pytest.mark.asyncio
async def test_conversation_summary_non_owner_denied(
    settings,
    db_session: AsyncSession,
) -> None:
    owner = await _user(db_session, email=f"owner-{uuid.uuid4().hex[:8]}@example.com")
    other = await _user(db_session, email=f"other-{uuid.uuid4().hex[:8]}@example.com")
    conversation = Conversation(
        id=uuid.uuid4(),
        user_id=owner.id,
        title="Private",
        status=ConversationStatus.active,
    )
    db_session.add(conversation)
    await db_session.flush()

    tool = ConversationSummaryTool()
    ctx = ToolExecutionContext(
        session=db_session,
        user_id=other.id,
        user_role=UserRole.user,
        llm_service=LLMService(settings=settings, provider=FakeLLMProvider()),
        active_tool_stack=["conversation_summary"],
    )
    with pytest.raises(ToolPermissionDeniedError):
        await tool.execute(
            ConversationSummaryInput(conversation_id=conversation.id),
            ctx,
        )


@pytest.mark.asyncio
async def test_conversation_summary_provider_failure(
    settings,
    db_session: AsyncSession,
) -> None:
    owner = await _user(db_session)
    conversation = Conversation(
        id=uuid.uuid4(),
        user_id=owner.id,
        title="Fail",
        status=ConversationStatus.active,
    )
    db_session.add(conversation)
    db_session.add(
        Message(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            user_id=owner.id,
            role=MessageRole.user,
            content="Hello",
            status=MessageStatus.complete,
            sequence_number=1,
        )
    )
    await db_session.flush()

    provider = FakeLLMProvider(fail_mode="generation")
    tool = ConversationSummaryTool()
    ctx = ToolExecutionContext(
        session=db_session,
        user_id=owner.id,
        user_role=UserRole.user,
        llm_service=LLMService(settings=settings, provider=provider),
        active_tool_stack=["conversation_summary"],
    )
    from app.tools.exceptions import ToolExecutionFailedError

    with pytest.raises(ToolExecutionFailedError):
        await tool.execute(
            ConversationSummaryInput(conversation_id=conversation.id),
            ctx,
        )


@pytest.mark.asyncio
async def test_knowledge_search_requires_retrieval_service(
    db_session: AsyncSession,
) -> None:
    tool = KnowledgeSearchTool()
    ctx = ToolExecutionContext(
        session=db_session,
        user_id=uuid.uuid4(),
        user_role=UserRole.user,
        retrieval_service=None,
        active_tool_stack=["knowledge_search"],
    )
    from app.tools.exceptions import ToolExecutionFailedError

    with pytest.raises(ToolExecutionFailedError, match="not configured"):
        await tool.execute(KnowledgeSearchInput(query="hello", limit=3), ctx)


def test_knowledge_search_input_limit_enforced() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        KnowledgeSearchInput(query="q", limit=50)
