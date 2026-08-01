"""Agent registry unit tests (Phase 9.1)."""

from __future__ import annotations

import pytest
from app.agents.definitions import (
    ConversationAgent,
    CoordinatorAgent,
    SafetyAgent,
    create_default_agent_registry,
    create_system_agents,
)
from app.agents.exceptions import (
    AgentDisabledError,
    AgentNotFoundError,
    AgentPlanValidationError,
    AgentRegistryError,
)
from app.agents.registry import AgentRegistry, build_agent_registry
from app.agents.schemas import AgentPlan, AgentPlanTask


def test_registers_system_agents() -> None:
    registry = create_default_agent_registry()
    names = registry.names()
    assert names == [
        "conversation",
        "coordinator",
        "knowledge",
        "memory",
        "planning",
        "safety",
        "tool",
    ]


def test_rejects_duplicate_registration() -> None:
    registry = AgentRegistry()
    registry.register(CoordinatorAgent())
    with pytest.raises(AgentRegistryError, match="Duplicate"):
        registry.register(CoordinatorAgent())


def test_unknown_agent_rejected() -> None:
    registry = create_default_agent_registry()
    with pytest.raises(AgentNotFoundError):
        registry.get("invented_agent")
    with pytest.raises(AgentNotFoundError):
        registry.validate_agent_name("invented_agent")


def test_disabled_agent_unavailable() -> None:
    registry = create_default_agent_registry()
    registry.set_enabled("planning", False)
    with pytest.raises(AgentDisabledError):
        registry.require_enabled("planning")
    enabled = {agent.name for agent in registry.enabled_agents()}
    assert "planning" not in enabled
    assert "coordinator" in enabled


def test_required_coordinator_cannot_be_disabled() -> None:
    registry = create_default_agent_registry()
    with pytest.raises(AgentRegistryError, match="cannot be disabled"):
        registry.set_enabled("coordinator", False)
    with pytest.raises(AgentRegistryError, match="cannot be disabled"):
        registry.set_enabled("safety", False)


def test_safety_agent_cannot_be_bypassed_via_disable() -> None:
    registry = create_default_agent_registry()
    assert not registry.can_disable("safety")
    assert registry.get("safety").required_for_multi_agent is True


def test_agent_allowed_tools_restrictions() -> None:
    registry = create_default_agent_registry()
    knowledge = registry.get("knowledge")
    assert "knowledge_search" in registry.effective_allowed_tools(knowledge)
    tool_agent = registry.get("tool")
    tools = registry.effective_allowed_tools(tool_agent)
    assert "calculator" in tools
    assert "knowledge_search" not in tools


def test_valid_plan_accepted() -> None:
    registry = create_default_agent_registry()
    plan = AgentPlan(
        goal="Summarize document and calculate contingency",
        requires_multi_agent=True,
        reasoning_summary="Needs document retrieval and calculation",
        tasks=[
            AgentPlanTask(
                sequence=1,
                agent_name="knowledge",
                task_type="retrieve",
                objective="Retrieve authorized document context",
                allowed_tools=["knowledge_search"],
            ),
            AgentPlanTask(
                sequence=2,
                agent_name="tool",
                task_type="calculate",
                objective="Calculate 15 percent contingency",
                dependencies=[1],
                allowed_tools=["calculator"],
            ),
            AgentPlanTask(
                sequence=3,
                agent_name="conversation",
                task_type="synthesize",
                objective="Prepare final recommendation",
                dependencies=[1, 2],
            ),
        ],
        final_response_agent="conversation",
        estimated_steps=3,
    )
    registry.validate_plan(
        plan,
        max_tasks=8,
        max_depth=2,
        max_tool_calls=8,
        enabled_tool_names=frozenset({"knowledge_search", "calculator"}),
    )


def test_unknown_agent_plan_rejected() -> None:
    registry = create_default_agent_registry()
    plan = AgentPlan(
        goal="Hack the system",
        requires_multi_agent=True,
        reasoning_summary="Invalid agent",
        tasks=[
            AgentPlanTask(
                sequence=1,
                agent_name="shadow_agent",
                task_type="evil",
                objective="Do something unauthorized",
            )
        ],
    )
    with pytest.raises(AgentPlanValidationError, match="Unknown agent"):
        registry.validate_plan(plan, max_tasks=8, max_depth=2, max_tool_calls=8)


def test_disabled_agent_plan_rejected() -> None:
    registry = create_default_agent_registry()
    registry.set_enabled("knowledge", False)
    plan = AgentPlan(
        goal="Retrieve docs",
        requires_multi_agent=True,
        reasoning_summary="Uses disabled agent",
        tasks=[
            AgentPlanTask(
                sequence=1,
                agent_name="knowledge",
                task_type="retrieve",
                objective="Retrieve documents",
            )
        ],
    )
    with pytest.raises(AgentPlanValidationError, match="Disabled agent"):
        registry.validate_plan(plan, max_tasks=8, max_depth=2, max_tool_calls=8)


def test_invalid_dependency_rejected() -> None:
    registry = create_default_agent_registry()
    plan = AgentPlan(
        goal="Bad deps",
        requires_multi_agent=True,
        reasoning_summary="Missing dependency",
        tasks=[
            AgentPlanTask(
                sequence=1,
                agent_name="conversation",
                task_type="chat",
                objective="Respond",
                dependencies=[99],
            )
        ],
    )
    with pytest.raises(AgentPlanValidationError, match="unknown sequence"):
        registry.validate_plan(plan, max_tasks=8, max_depth=2, max_tool_calls=8)


def test_cyclic_plan_rejected() -> None:
    registry = create_default_agent_registry()
    # Dependencies must reference earlier sequences by our forward-check,
    # so craft a cycle via mutual deps that pass the earlier-sequence check
    # by using sequence numbers carefully — earlier-seq rule blocks classic
    # cycles, so verify excessive depth / invalid forward deps separately.
    # True cycle with earlier-only deps is impossible; verify forward dep fails.
    plan = AgentPlan(
        goal="Forward dep",
        requires_multi_agent=True,
        reasoning_summary="Forward dependency",
        tasks=[
            AgentPlanTask(
                sequence=1,
                agent_name="conversation",
                task_type="a",
                objective="First",
                dependencies=[2],
            ),
            AgentPlanTask(
                sequence=2,
                agent_name="conversation",
                task_type="b",
                objective="Second",
            ),
        ],
    )
    with pytest.raises(AgentPlanValidationError, match="earlier task"):
        registry.validate_plan(plan, max_tasks=8, max_depth=2, max_tool_calls=8)


def test_excessive_task_count_rejected() -> None:
    registry = create_default_agent_registry()
    tasks = [
        AgentPlanTask(
            sequence=i,
            agent_name="conversation",
            task_type="chat",
            objective=f"Step {i}",
        )
        for i in range(1, 6)
    ]
    plan = AgentPlan(
        goal="Too many",
        requires_multi_agent=True,
        reasoning_summary="Exceeds max",
        tasks=tasks,
    )
    with pytest.raises(AgentPlanValidationError, match="maximum task count"):
        registry.validate_plan(plan, max_tasks=3, max_depth=2, max_tool_calls=8)


def test_excessive_depth_rejected() -> None:
    registry = create_default_agent_registry()
    plan = AgentPlan(
        goal="Deep chain",
        requires_multi_agent=True,
        reasoning_summary="Too deep",
        tasks=[
            AgentPlanTask(
                sequence=1,
                agent_name="conversation",
                task_type="a",
                objective="One",
            ),
            AgentPlanTask(
                sequence=2,
                agent_name="conversation",
                task_type="b",
                objective="Two",
                dependencies=[1],
            ),
            AgentPlanTask(
                sequence=3,
                agent_name="conversation",
                task_type="c",
                objective="Three",
                dependencies=[2],
            ),
            AgentPlanTask(
                sequence=4,
                agent_name="conversation",
                task_type="d",
                objective="Four",
                dependencies=[3],
            ),
        ],
    )
    with pytest.raises(AgentPlanValidationError, match="maximum depth"):
        registry.validate_plan(plan, max_tasks=8, max_depth=2, max_tool_calls=8)


def test_unauthorized_tool_rejected() -> None:
    registry = create_default_agent_registry()
    plan = AgentPlan(
        goal="Bad tool",
        requires_multi_agent=True,
        reasoning_summary="Tool not allowed for agent",
        tasks=[
            AgentPlanTask(
                sequence=1,
                agent_name="conversation",
                task_type="chat",
                objective="Try calculator",
                allowed_tools=["calculator"],
            )
        ],
    )
    with pytest.raises(AgentPlanValidationError, match="not allowed"):
        registry.validate_plan(plan, max_tasks=8, max_depth=2, max_tool_calls=8)


def test_invalid_final_response_agent_rejected() -> None:
    registry = create_default_agent_registry()
    plan = AgentPlan(
        goal="Bad final",
        requires_multi_agent=True,
        reasoning_summary="Unknown final agent",
        tasks=[
            AgentPlanTask(
                sequence=1,
                agent_name="conversation",
                task_type="chat",
                objective="Respond",
            )
        ],
        final_response_agent="ghost",
    )
    with pytest.raises(AgentPlanValidationError, match="Final response agent"):
        registry.validate_plan(plan, max_tasks=8, max_depth=2, max_tool_calls=8)


def test_build_registry_from_iterable() -> None:
    registry = build_agent_registry([ConversationAgent(), SafetyAgent()])
    assert registry.names() == ["conversation", "safety"]
    assert len(create_system_agents()) == 7
