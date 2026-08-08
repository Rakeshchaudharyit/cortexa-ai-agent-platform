"""Phase 9.8 deterministic planning policy tests."""

from __future__ import annotations

import pytest

from app.agents.definitions import create_default_agent_registry
from app.agents.schemas import AgentComplexityDecision
from app.agents.specialists.planning import PlanningSpecialist
from app.core.config import Settings


def _forced_decision() -> AgentComplexityDecision:
    return AgentComplexityDecision(
        execution_mode="multi_agent",
        confidence=1.0,
        reason_codes=["user_forced_multi_agent", "profile_fast"],
        required_capabilities=["planning", "knowledge", "response"],
        suggested_agents=["planning", "knowledge", "conversation"],
        requires_planning=True,
        safe_summary="User explicitly requested coordinated specialist execution",
    )


def _planner(settings: Settings) -> PlanningSpecialist:
    return PlanningSpecialist(
        settings=settings,
        registry=create_default_agent_registry(),
        llm_service=None,
    )


@pytest.mark.asyncio
async def test_forced_knowledge_recommendation_is_deterministic(settings: Settings) -> None:
    planner = _planner(settings)
    plan = await planner.create_plan(
        user_request=(
            "Review the available knowledge, identify architecture themes, compare options, "
            "analyze risks, and provide a prioritized recommendation."
        ),
        decision=_forced_decision(),
        enabled_tool_names=frozenset({"calculator", "current_datetime"}),
        execution_profile="fast",
    )

    assert plan.planning_strategy == "deterministic"
    assert [task.agent_name for task in plan.tasks] == ["knowledge", "conversation"]
    assert len(plan.tasks) == 2
    assert plan.tasks[-1].dependencies == [1]
    assert all(task.maximum_retries == 0 for task in plan.tasks)


@pytest.mark.asyncio
async def test_deterministic_plan_never_empty(settings: Settings) -> None:
    planner = _planner(settings)
    plan = await planner.create_plan(
        user_request="Compare the implementation options and recommend a strategy.",
        decision=_forced_decision(),
        enabled_tool_names=frozenset(),
        execution_profile="fast",
    )

    assert plan.tasks
    assert plan.tasks[-1].agent_name == "conversation"
    assert plan.estimated_steps == len(plan.tasks)


@pytest.mark.asyncio
async def test_tool_workflow_selects_only_enabled_tools(settings: Settings) -> None:
    planner = _planner(settings)
    plan = await planner.create_plan(
        user_request="Review the report, calculate 15 percent contingency, and recommend an option.",
        decision=_forced_decision(),
        enabled_tool_names=frozenset({"calculator"}),
        execution_profile="balanced",
    )

    agents = [task.agent_name for task in plan.tasks]
    assert agents == ["knowledge", "tool", "conversation"]
    assert plan.tasks[1].allowed_tools == ["calculator"]
    assert plan.tasks[-1].dependencies == [1, 2]


@pytest.mark.asyncio
async def test_ambiguous_request_uses_safe_fallback_without_llm(settings: Settings) -> None:
    planner = _planner(settings)
    decision = AgentComplexityDecision(
        execution_mode="multi_agent",
        confidence=0.8,
        reason_codes=["unusual_combo"],
        suggested_agents=["conversation"],
        requires_planning=True,
        safe_summary="Ambiguous request",
    )
    plan = await planner.create_plan(
        user_request="Do the thing in the best way.",
        decision=decision,
        enabled_tool_names=frozenset(),
        execution_profile="fast",
    )

    assert plan.planning_strategy == "fallback"
    assert [task.agent_name for task in plan.tasks] == ["conversation"]
