"""Phase 9.2 planning agent tests."""

from __future__ import annotations

import pytest
from app.agents.definitions import create_default_agent_registry
from app.agents.exceptions import AgentPlanValidationError
from app.agents.schemas import AgentComplexityDecision, AgentPlan, AgentPlanTask
from app.agents.specialists.planning import PlanningSpecialist
from app.core.config import Settings
from app.services.llm import LLMService

from tests.fakes.llm import FakeLLMProvider, FakeLLMTurn


def _planner(settings: Settings, llm: FakeLLMProvider | None = None) -> PlanningSpecialist:
    registry = create_default_agent_registry()
    llm_service = LLMService(settings=settings, provider=llm) if llm is not None else None
    return PlanningSpecialist(settings=settings, registry=registry, llm_service=llm_service)


def _multi_decision(*codes: str) -> AgentComplexityDecision:
    return AgentComplexityDecision(
        execution_mode="multi_agent",
        confidence=0.95,
        reason_codes=list(codes),
        suggested_agents=["knowledge", "tool", "conversation"],
        requires_planning=True,
        safe_summary="Needs multiple specialists",
    )


@pytest.mark.asyncio
async def test_deterministic_knowledge_tool_conversation_plan(settings: Settings) -> None:
    planner = _planner(settings)
    plan = await planner.create_plan(
        user_request="Review the contract, calculate 15% contingency, prepare a recommendation.",
        decision=_multi_decision("combo_knowledge_tool", "combo_document_calc_recommend"),
        enabled_tool_names=frozenset({"calculator", "current_datetime"}),
        selected_document_ids=["11111111-1111-1111-1111-111111111111"],
    )
    agents = [t.agent_name for t in plan.tasks]
    assert agents == ["knowledge", "tool", "conversation"]
    assert plan.final_response_agent == "conversation"
    assert "hidden" not in plan.reasoning_summary.lower()
    assert "chain" not in plan.reasoning_summary.lower()


@pytest.mark.asyncio
async def test_deterministic_memory_knowledge_conversation_plan(settings: Settings) -> None:
    planner = _planner(settings)
    decision = AgentComplexityDecision(
        execution_mode="multi_agent",
        confidence=0.95,
        reason_codes=["combo_knowledge_memory"],
        suggested_agents=["memory", "knowledge", "conversation"],
        requires_planning=True,
        safe_summary="Needs memory and knowledge",
    )
    plan = await planner.create_plan(
        user_request="Use my saved preferences and this document to draft a proposal.",
        decision=decision,
        enabled_tool_names=frozenset(),
        selected_document_ids=["11111111-1111-1111-1111-111111111111"],
        memory_enabled=True,
    )
    agents = [t.agent_name for t in plan.tasks]
    assert agents[:3] == ["memory", "knowledge", "conversation"] or (
        "memory" in agents and "knowledge" in agents and agents[-1] == "conversation"
    )


@pytest.mark.asyncio
async def test_registered_agents_only_in_template(settings: Settings) -> None:
    planner = _planner(settings)
    plan = await planner.create_plan(
        user_request="Review docs and calculate contingency then recommend.",
        decision=_multi_decision("combo_knowledge_tool"),
        enabled_tool_names=frozenset({"calculator"}),
        selected_document_ids=["11111111-1111-1111-1111-111111111111"],
    )
    for task in plan.tasks:
        assert task.agent_name in planner.registry.names()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_disabled_agent_plan_rejected(settings: Settings) -> None:
    planner = _planner(settings)
    assert planner.registry is not None
    planner.registry.set_enabled("knowledge", False)
    with pytest.raises(AgentPlanValidationError):
        planner.registry.validate_plan(
            AgentPlan(
                goal="x",
                reasoning_summary="Needs knowledge",
                tasks=[
                    AgentPlanTask(
                        sequence=1,
                        agent_name="knowledge",
                        task_type="retrieve",
                        objective="Retrieve",
                    )
                ],
            ),
            max_tasks=8,
            max_depth=2,
            max_tool_calls=8,
        )


@pytest.mark.asyncio
async def test_invalid_dependency_and_cycle_rejected(settings: Settings) -> None:
    planner = _planner(settings)
    assert planner.registry is not None
    with pytest.raises(AgentPlanValidationError):
        planner.registry.validate_plan(
            AgentPlan(
                goal="x",
                reasoning_summary="Bad dependency",
                tasks=[
                    AgentPlanTask(
                        sequence=1,
                        agent_name="conversation",
                        task_type="respond",
                        objective="A",
                        dependencies=[2],
                    ),
                    AgentPlanTask(
                        sequence=2,
                        agent_name="conversation",
                        task_type="respond",
                        objective="B",
                    ),
                ],
            ),
            max_tasks=8,
            max_depth=2,
            max_tool_calls=8,
        )
    with pytest.raises(AgentPlanValidationError, match="earlier task"):
        planner.registry.validate_plan(
            AgentPlan(
                goal="x",
                reasoning_summary="Cycle",
                tasks=[
                    AgentPlanTask(
                        sequence=1,
                        agent_name="knowledge",
                        task_type="retrieve",
                        objective="A",
                        dependencies=[2],
                    ),
                    AgentPlanTask(
                        sequence=2,
                        agent_name="tool",
                        task_type="compute",
                        objective="B",
                        dependencies=[1],
                        allowed_tools=["calculator"],
                    ),
                ],
            ),
            max_tasks=8,
            max_depth=4,
            max_tool_calls=8,
        )


@pytest.mark.asyncio
async def test_task_count_and_depth_and_tools_limits(settings: Settings) -> None:
    planner = _planner(settings)
    assert planner.registry is not None
    too_many = AgentPlan(
        goal="x",
        reasoning_summary="Too many",
        tasks=[
            AgentPlanTask(
                sequence=i,
                agent_name="conversation",
                task_type="respond",
                objective=f"step {i}",
            )
            for i in range(1, 12)
        ],
    )
    with pytest.raises(AgentPlanValidationError) as exc:
        planner.registry.validate_plan(too_many, max_tasks=8, max_depth=2, max_tool_calls=8)
    assert exc.value.code == "agent_plan_too_many_tasks"

    deep = AgentPlan(
        goal="x",
        reasoning_summary="Deep",
        tasks=[
            AgentPlanTask(sequence=1, agent_name="knowledge", task_type="r", objective="a"),
            AgentPlanTask(
                sequence=2,
                agent_name="tool",
                task_type="c",
                objective="b",
                dependencies=[1],
                allowed_tools=["calculator"],
            ),
            AgentPlanTask(
                sequence=3,
                agent_name="conversation",
                task_type="s",
                objective="c",
                dependencies=[2],
            ),
            AgentPlanTask(
                sequence=4,
                agent_name="conversation",
                task_type="s",
                objective="d",
                dependencies=[3],
            ),
        ],
    )
    with pytest.raises(AgentPlanValidationError) as exc2:
        planner.registry.validate_plan(deep, max_tasks=8, max_depth=2, max_tool_calls=8)
    assert exc2.value.code == "agent_plan_excessive_depth"

    bad_tool = AgentPlan(
        goal="x",
        reasoning_summary="Bad tool",
        tasks=[
            AgentPlanTask(
                sequence=1,
                agent_name="tool",
                task_type="c",
                objective="calc",
                allowed_tools=["knowledge_search"],
            )
        ],
    )
    with pytest.raises(AgentPlanValidationError) as exc3:
        planner.registry.validate_plan(bad_tool, max_tasks=8, max_depth=2, max_tool_calls=8)
    assert exc3.value.code == "agent_plan_unauthorized_tool"


@pytest.mark.asyncio
async def test_final_response_agent_validated(settings: Settings) -> None:
    planner = _planner(settings)
    assert planner.registry is not None
    with pytest.raises(AgentPlanValidationError) as exc:
        planner.registry.validate_plan(
            AgentPlan(
                goal="x",
                reasoning_summary="Bad final",
                tasks=[
                    AgentPlanTask(
                        sequence=1,
                        agent_name="conversation",
                        task_type="respond",
                        objective="hi",
                    )
                ],
                final_response_agent="not_an_agent",
            ),
            max_tasks=8,
            max_depth=2,
            max_tool_calls=8,
        )
    assert exc.value.code == "agent_plan_invalid_final_agent"


@pytest.mark.asyncio
async def test_malformed_model_plan_rejected_then_fallback(settings: Settings) -> None:
    llm = FakeLLMProvider(scripted_turns=[FakeLLMTurn(content="not-json")])
    planner = _planner(settings, llm)
    # No template match → LLM path → malformed → fallback conversation plan
    decision = AgentComplexityDecision(
        execution_mode="multi_agent",
        confidence=0.9,
        reason_codes=["unusual_combo"],
        suggested_agents=["conversation"],
        requires_planning=True,
        safe_summary="Unusual",
    )
    plan = await planner.create_plan(
        user_request="Do something oddly complex with orchestration pieces.",
        decision=decision,
        enabled_tool_names=frozenset({"calculator"}),
    )
    assert plan.tasks[0].agent_name == "conversation"
    assert plan.requires_multi_agent is False


@pytest.mark.asyncio
async def test_one_replan_attempt_only(settings: Settings) -> None:
    settings_obj = settings
    # Force max_replans=1 and two malformed outputs then valid — only one retry.
    object.__setattr__(settings_obj, "agent_max_replans", 1) if False else None
    llm = FakeLLMProvider(
        scripted_turns=[
            FakeLLMTurn(content="{bad"),
            FakeLLMTurn(content="{bad"),
            FakeLLMTurn(
                content=(
                    '{"goal":"g","reasoning_summary":"Safe summary.",'
                    '"tasks":[{"sequence":1,"agent_name":"conversation","task_type":"respond",'
                    '"objective":"Answer","dependencies":[],"allowed_tools":[],'
                    '"expected_output":"answer","requires_approval":false}],'
                    '"final_response_agent":"conversation","estimated_steps":1,'
                    '"requires_approval":false}'
                )
            ),
        ]
    )
    planner = _planner(settings_obj, llm)
    # Monkeypatch settings max_replans via planner.settings
    assert planner.settings is not None
    planner.settings.__dict__["agent_max_replans"] = 1
    decision = AgentComplexityDecision(
        execution_mode="multi_agent",
        confidence=0.9,
        reason_codes=["unusual_combo"],
        suggested_agents=["conversation"],
        requires_planning=True,
        safe_summary="Unusual",
    )
    plan = await planner.create_plan(
        user_request="Orchestrate an unusual multi-capability workflow please.",
        decision=decision,
        enabled_tool_names=frozenset(),
    )
    # With max_replans=1: attempt 0 malformed, attempt 1 malformed → fallback (3rd not used)
    assert plan.final_response_agent == "conversation"
    assert llm.generate_calls <= 2


@pytest.mark.asyncio
async def test_safe_reasoning_summary_no_hidden_reasoning(settings: Settings) -> None:
    planner = _planner(settings)
    plan = await planner.create_plan(
        user_request="Review contract and calculate contingency then recommend.",
        decision=_multi_decision("combo_knowledge_tool", "combo_document_calc_recommend"),
        enabled_tool_names=frozenset({"calculator"}),
        selected_document_ids=["11111111-1111-1111-1111-111111111111"],
    )
    dumped = plan.model_dump()
    assert "hidden_reasoning" not in dumped
    assert "chain_of_thought" not in dumped
    assert len(plan.reasoning_summary) <= 500
