"""Agent orchestrator loop tests with deterministic FakeLLMProvider."""

from __future__ import annotations

import uuid

import pytest
from app.agents.orchestrator import AgentOrchestrator
from app.agents.schemas import AgentRunConfig
from app.core.config import Settings
from app.llm.schemas import ChatMessage, MessageRole, StreamEventType, ToolCallRequest
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.services.llm import LLMService
from app.tools.builtins import create_builtin_registry
from app.tools.executor import ToolExecutor
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes.llm import FakeLLMProvider, FakeLLMTurn


async def _user(session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"agent-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Agent User",
        password_hash="not-a-real-hash",
        role=UserRole.user,
        status=UserStatus.active,
    )
    session.add(user)
    await session.flush()
    return user


def _orchestrator(settings: Settings, provider: FakeLLMProvider) -> AgentOrchestrator:
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
async def test_no_tool_response_works(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    settings.agent_max_tool_iterations = 3
    provider = FakeLLMProvider(generate_content="Hello without tools")
    orch = _orchestrator(settings, provider)
    user = await _user(db_session)
    result = await orch.run(
        session=db_session,
        user=user,
        messages=[ChatMessage(role=MessageRole.user, content="Hi")],
        system=None,
        conversation_id=None,
        message_id=None,
        allowed_document_ids=None,
        config=AgentRunConfig(selected_tool_names=[]),
    )
    assert result.content == "Hello without tools"
    assert result.tool_execution_ids == []
    assert provider.stream_calls >= 1
    assert provider.generate_calls == 0
    assert provider.last_request is not None
    assert provider.last_request.tools in (None, [])


@pytest.mark.asyncio
async def test_single_tool_call_and_result_returned(
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
                        arguments={"expression": "(2450 * 18) / 100"},
                    )
                ],
            ),
            FakeLLMTurn(
                content="18% of 2450 is 441.",
                finish_reason="stop",
            ),
        ]
    )
    orch = _orchestrator(settings, provider)
    user = await _user(db_session)
    result = await orch.run(
        session=db_session,
        user=user,
        messages=[ChatMessage(role=MessageRole.user, content="What is 18% of 2450?")],
        system=None,
        conversation_id=None,
        message_id=None,
        allowed_document_ids=None,
        config=AgentRunConfig(selected_tool_names=["calculator"]),
    )
    assert "441" in result.content
    assert len(result.tool_execution_ids) == 1
    assert any(m.role == MessageRole.tool for m in provider.requests[1].messages)


@pytest.mark.asyncio
async def test_two_step_tool_sequence(
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
                        arguments={"expression": "1 + 1"},
                    )
                ],
            ),
            FakeLLMTurn(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="c2",
                        name="calculator",
                        arguments={"expression": "2 + 2"},
                    )
                ],
            ),
            FakeLLMTurn(content="Done with both.", finish_reason="stop"),
        ]
    )
    orch = _orchestrator(settings, provider)
    user = await _user(db_session)
    result = await orch.run(
        session=db_session,
        user=user,
        messages=[ChatMessage(role=MessageRole.user, content="Do two calcs")],
        system=None,
        conversation_id=None,
        message_id=None,
        allowed_document_ids=None,
        config=AgentRunConfig(max_iterations=3, selected_tool_names=["calculator"]),
    )
    assert result.content == "Done with both."
    assert len(result.tool_execution_ids) == 2


@pytest.mark.asyncio
async def test_invalid_tool_name_handled(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    provider = FakeLLMProvider(
        scripted_turns=[
            FakeLLMTurn(
                content="",
                tool_calls=[ToolCallRequest(id="c1", name="hallucinated_tool", arguments={})],
            ),
            FakeLLMTurn(content="I could not use that tool.", finish_reason="stop"),
        ]
    )
    orch = _orchestrator(settings, provider)
    user = await _user(db_session)
    result = await orch.run(
        session=db_session,
        user=user,
        messages=[ChatMessage(role=MessageRole.user, content="Call bad tool")],
        system=None,
        conversation_id=None,
        message_id=None,
        allowed_document_ids=None,
        config=AgentRunConfig(selected_tool_names=["calculator"]),
    )
    assert "could not use" in result.content.lower() or result.content
    assert any(
        m.role == MessageRole.tool and "not authorized" in (m.content or "").lower()
        for req in provider.requests
        for m in req.messages
    )


@pytest.mark.asyncio
async def test_invalid_arguments_handled(
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
                        arguments={"expression": "not@@valid"},
                    )
                ],
            ),
            FakeLLMTurn(content="Sorry, calculation failed.", finish_reason="stop"),
        ]
    )
    orch = _orchestrator(settings, provider)
    user = await _user(db_session)
    result = await orch.run(
        session=db_session,
        user=user,
        messages=[ChatMessage(role=MessageRole.user, content="bad calc")],
        system=None,
        conversation_id=None,
        message_id=None,
        allowed_document_ids=None,
        config=AgentRunConfig(selected_tool_names=["calculator"]),
    )
    assert result.content
    assert any(m.role == MessageRole.tool for req in provider.requests for m in req.messages)


@pytest.mark.asyncio
async def test_max_iterations_stops_loop(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    settings.agent_max_tool_iterations = 2
    provider = FakeLLMProvider(
        scripted_turns=[
            FakeLLMTurn(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="c1",
                        name="calculator",
                        arguments={"expression": "1+1"},
                    )
                ],
            ),
            FakeLLMTurn(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="c2",
                        name="calculator",
                        arguments={"expression": "2+2"},
                    )
                ],
            ),
            FakeLLMTurn(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="c3",
                        name="calculator",
                        arguments={"expression": "3+3"},
                    )
                ],
            ),
        ]
    )
    orch = _orchestrator(settings, provider)
    user = await _user(db_session)
    result = await orch.run(
        session=db_session,
        user=user,
        messages=[ChatMessage(role=MessageRole.user, content="loop")],
        system=None,
        conversation_id=None,
        message_id=None,
        allowed_document_ids=None,
        config=AgentRunConfig(max_iterations=2, selected_tool_names=["calculator"]),
    )
    assert "maximum number of tool steps" in result.content
    assert provider.generate_calls == 2


@pytest.mark.asyncio
async def test_streaming_events_ordered(
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
                        arguments={"expression": "5*5"},
                    )
                ],
            ),
            FakeLLMTurn(content="25", finish_reason="stop"),
        ]
    )
    orch = _orchestrator(settings, provider)
    user = await _user(db_session)
    events = []
    deltas = 0
    async for event in orch.stream(
        session=db_session,
        user=user,
        messages=[ChatMessage(role=MessageRole.user, content="5*5")],
        system=None,
        conversation_id=None,
        message_id=None,
        allowed_document_ids=None,
        config=AgentRunConfig(selected_tool_names=["calculator"]),
    ):
        events.append(event.event)
        if event.event == StreamEventType.delta:
            deltas += 1

    assert events[0] == StreamEventType.agent_started
    assert StreamEventType.tool_call_started in events
    assert StreamEventType.tool_execution_succeeded in events
    assert StreamEventType.delta in events
    assert deltas >= 1
    assert events[-1] == StreamEventType.agent_completed
