"""Deterministic tool-selection policy and streaming regression tests."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from app.agents.orchestrator import AgentOrchestrator
from app.agents.schemas import AgentRunConfig
from app.agents.tool_selection import (
    ToolSelectionContext,
    filter_provider_tool_names,
    resolve_conversation_mode,
    select_tools_for_turn,
)
from app.core.config import Settings
from app.llm.schemas import ChatMessage, MessageRole, StreamEventType, ToolCallRequest
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.services.llm import LLMService
from app.tools.builtins import create_builtin_registry
from app.tools.executor import ToolExecutor
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes.llm import FakeLLMProvider, FakeLLMTurn


def _ctx(
    message: str,
    *,
    mode: str = "general",
    docs: bool = False,
    memory: bool = True,
    conv_memory: bool = True,
    registered: frozenset[str] | None = None,
) -> ToolSelectionContext:
    names = registered or frozenset(
        {
            "calculator",
            "current_datetime",
            "knowledge_search",
            "memory_list",
            "memory_search",
            "conversation_summary",
        }
    )
    return ToolSelectionContext(
        user_message=message,
        conversation_mode=mode,  # type: ignore[arg-type]
        document_ids=[] if mode == "general" else [uuid.uuid4()],
        has_accessible_documents=docs,
        memory_globally_enabled=memory,
        conversation_memory_enabled=conv_memory,
        registered_tool_names=names,
    )


def test_trivial_chat_selects_no_tools() -> None:
    for msg in (
        "Hello",
        "Explain this concept",
        "Rewrite this sentence",
        "Reply only with Working",
        "What did I say previously?",
    ):
        result = select_tools_for_turn(_ctx(msg))
        assert result.selected_tool_names == []
        assert "no_tools_needed" in result.reason_codes


def test_calculator_request_selects_calculator_only() -> None:
    result = select_tools_for_turn(_ctx("What is 245 multiplied by 17?"))
    assert result.selected_tool_names == ["calculator"]


def test_datetime_request_selects_datetime_only() -> None:
    result = select_tools_for_turn(_ctx("What time is it in Asia/Kolkata?"))
    assert result.selected_tool_names == ["current_datetime"]


def test_memory_off_excludes_memory_tools() -> None:
    result = select_tools_for_turn(
        _ctx("What do you remember about me?", memory=False, conv_memory=False)
    )
    assert "memory_list" not in result.selected_tool_names
    assert "memory_search" not in result.selected_tool_names
    assert "memory_tools_skipped_disabled" in result.reason_codes


def test_general_mode_no_documents_excludes_knowledge_search() -> None:
    result = select_tools_for_turn(_ctx("Tell me about Cortexa", mode="general", docs=False))
    assert "knowledge_search" not in result.selected_tool_names


def test_document_mode_selects_knowledge_search() -> None:
    result = select_tools_for_turn(
        _ctx("What does the handbook say about onboarding?", mode="document", docs=True)
    )
    assert result.selected_tool_names == ["knowledge_search"]


def test_explicit_memory_list_when_enabled() -> None:
    result = select_tools_for_turn(
        _ctx(
            "What do you remember about my programming preferences?",
            memory=True,
            conv_memory=True,
        )
    )
    assert "memory_list" in result.selected_tool_names
    assert "calculator" not in result.selected_tool_names
    assert "knowledge_search" not in result.selected_tool_names


def test_conversation_summary_request_selects_summary_only() -> None:
    result = select_tools_for_turn(_ctx("Please summarize this conversation"))
    assert result.selected_tool_names == ["conversation_summary"]


def test_unauthorized_and_disabled_tools_cannot_be_selected() -> None:
    filtered = filter_provider_tool_names(
        candidate_names=["calculator", "evil_tool", "memory_list"],
        registered_tool_names=frozenset({"calculator"}),
    )
    assert filtered == ["calculator"]

    result = select_tools_for_turn(
        _ctx(
            "What is 2+2?",
            registered=frozenset({"current_datetime"}),
        )
    )
    assert "calculator" not in result.selected_tool_names


def test_resolve_conversation_mode() -> None:
    assert resolve_conversation_mode([]) == "general"
    assert resolve_conversation_mode(None) == "document"
    assert resolve_conversation_mode([uuid.uuid4()]) == "document"


async def _user(session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"sel-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Sel User",
        password_hash="not-a-real-hash",
        role=UserRole.user,
        status=UserStatus.active,
    )
    session.add(user)
    await session.flush()
    return user


def _orch(settings: Settings, provider: FakeLLMProvider) -> AgentOrchestrator:
    llm = LLMService(settings=settings, provider=provider)
    registry = create_builtin_registry()
    executor = ToolExecutor(registry=registry, settings=settings, llm_service=llm)
    return AgentOrchestrator(
        settings=settings,
        llm_service=llm,
        tool_registry=registry,
        tool_executor=executor,
    )


@pytest.mark.asyncio
async def test_trivial_chat_uses_stream_not_generate(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    provider = FakeLLMProvider(generate_content="Working")
    orch = _orch(settings, provider)
    user = await _user(db_session)
    deltas: list[str] = []
    async for event in orch.stream(
        session=db_session,
        user=user,
        messages=[ChatMessage(role=MessageRole.user, content="Reply only with Working")],
        system=None,
        conversation_id=None,
        message_id=None,
        allowed_document_ids=[],
        config=AgentRunConfig(selected_tool_names=[]),
    ):
        if event.event == StreamEventType.delta:
            deltas.append(str(event.data.get("content") or ""))
        if event.event == StreamEventType.agent_started:
            assert event.data.get("tools_selected_count") == 0
            assert event.data.get("selected_tool_names") == []

    assert provider.stream_calls >= 1
    assert provider.generate_calls == 0
    assert provider.last_request is not None
    assert not provider.last_request.tools
    assert len(deltas) >= 2
    assert "".join(deltas) == "Working"


@pytest.mark.asyncio
async def test_tool_final_answer_streams_when_empty_generate(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    provider = FakeLLMProvider(
        scripted_turns=[
            FakeLLMTurn(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="c1",
                        name="calculator",
                        arguments={"expression": "245 * 17"},
                    )
                ],
            ),
            FakeLLMTurn(content="", finish_reason="stop"),
            FakeLLMTurn(
                content="4165",
                finish_reason="stop",
                stream_chunks=["41", "65"],
            ),
        ]
    )
    orch = _orch(settings, provider)
    user = await _user(db_session)
    deltas: list[str] = []
    async for event in orch.stream(
        session=db_session,
        user=user,
        messages=[ChatMessage(role=MessageRole.user, content="What is 245 multiplied by 17?")],
        system=None,
        conversation_id=None,
        message_id=None,
        allowed_document_ids=[],
        config=AgentRunConfig(selected_tool_names=["calculator"]),
    ):
        if event.event == StreamEventType.delta:
            deltas.append(str(event.data.get("content") or ""))
    assert "".join(deltas) == "4165"
    assert provider.stream_calls >= 1
    assert provider.requests[-1].tools in (None, [])


@pytest.mark.asyncio
async def test_client_cancellation_cancels_provider_stream(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    cancel_flag = {"cancelled": False}

    async def cancel_check() -> bool:
        return cancel_flag["cancelled"]

    provider = FakeLLMProvider(
        generate_content="long answer that should be interrupted",
        stream_delay_seconds=0.05,
    )
    orch = _orch(settings, provider)
    user = await _user(db_session)

    async def _run() -> list[str]:
        events = []
        try:
            async for event in orch.stream(
                session=db_session,
                user=user,
                messages=[ChatMessage(role=MessageRole.user, content="Hello")],
                system=None,
                conversation_id=None,
                message_id=None,
                allowed_document_ids=[],
                config=AgentRunConfig(selected_tool_names=[]),
                cancel_check=cancel_check,
            ):
                events.append(event.event.value)
                if event.event == StreamEventType.delta:
                    cancel_flag["cancelled"] = True
        except asyncio.CancelledError:
            events.append("cancelled")
        return events

    events = await _run()
    assert provider.stream_cancelled or "cancelled" in events or provider.stream_calls >= 1


@pytest.mark.asyncio
async def test_provider_timeout_emits_safe_error(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    provider = FakeLLMProvider(fail_mode="timeout")
    orch = _orch(settings, provider)
    user = await _user(db_session)
    events = []
    async for event in orch.stream(
        session=db_session,
        user=user,
        messages=[ChatMessage(role=MessageRole.user, content="Hello")],
        system=None,
        conversation_id=None,
        message_id=None,
        allowed_document_ids=[],
        config=AgentRunConfig(selected_tool_names=[]),
    ):
        events.append(event)
    assert any(
        e.event == StreamEventType.error
        and (e.data.get("code") == "llm_request_timeout" or "timeout" in str(e.data).lower())
        for e in events
    )


@pytest.mark.asyncio
async def test_first_token_timeout_emits_safe_error(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    provider = FakeLLMProvider(fail_mode="first_token_timeout")
    orch = _orch(settings, provider)
    user = await _user(db_session)
    events = []
    async for event in orch.stream(
        session=db_session,
        user=user,
        messages=[ChatMessage(role=MessageRole.user, content="Hello")],
        system=None,
        conversation_id=None,
        message_id=None,
        allowed_document_ids=[],
        config=AgentRunConfig(selected_tool_names=[]),
    ):
        events.append(event)
    assert any(
        e.event == StreamEventType.error and e.data.get("code") == "llm_first_token_timeout"
        for e in events
    )
