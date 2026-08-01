"""Deterministic server-side agent registry — no dynamic imports or model-created agents."""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.agents.base import AgentRuntimeOverride, BaseAgent
from app.agents.capabilities import REQUIRED_MULTI_AGENT_KEYS, SYSTEM_AGENT_KEYS
from app.agents.exceptions import (
    AgentDisabledError,
    AgentNotFoundError,
    AgentPlanValidationError,
    AgentRegistryError,
)
from app.agents.schemas import AgentDefinitionView, AgentPlan, AgentPlanTask

_AGENT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


class AgentRegistry:
    """In-memory registry of server-approved specialist agents.

    Create a fresh instance per application (or per test). Duplicate names are
    rejected. Models cannot invent agent names or supply class paths.
    """

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self._overrides: dict[str, AgentRuntimeOverride] = {}

    def register(self, agent: BaseAgent) -> None:
        name = agent.name
        if not _AGENT_KEY_RE.match(name):
            raise AgentRegistryError(
                f"Invalid agent name '{name}': must match {_AGENT_KEY_RE.pattern}"
            )
        if name in self._agents:
            raise AgentRegistryError(f"Duplicate agent name '{name}'")
        self._agents[name] = agent

    def unregister(self, name: str) -> None:
        self._agents.pop(name, None)
        self._overrides.pop(name, None)

    def clear(self) -> None:
        self._agents.clear()
        self._overrides.clear()

    def apply_overrides(self, overrides: dict[str, AgentRuntimeOverride]) -> None:
        self._overrides = dict(overrides)

    def clear_overrides(self) -> None:
        self._overrides.clear()

    def get_override(self, name: str) -> AgentRuntimeOverride | None:
        return self._overrides.get(name)

    def get(self, name: str) -> BaseAgent:
        agent = self._agents.get(name)
        if agent is None:
            raise AgentNotFoundError(name)
        return agent

    def has(self, name: str) -> bool:
        return name in self._agents

    def validate_agent_name(self, name: str) -> None:
        if name not in self._agents:
            raise AgentNotFoundError(name)

    def is_effectively_enabled(self, agent: BaseAgent) -> bool:
        override = self._overrides.get(agent.name)
        if override is not None and override.enabled is not None:
            return bool(override.enabled)
        return bool(agent.enabled)

    def effective_timeout(self, agent: BaseAgent) -> int:
        override = self._overrides.get(agent.name)
        if override is not None and override.timeout_seconds is not None:
            return int(override.timeout_seconds)
        return int(agent.timeout_seconds)

    def effective_maximum_steps(self, agent: BaseAgent) -> int:
        override = self._overrides.get(agent.name)
        if override is not None and override.maximum_steps is not None:
            return int(override.maximum_steps)
        return int(agent.maximum_steps)

    def effective_allowed_tools(self, agent: BaseAgent) -> frozenset[str]:
        override = self._overrides.get(agent.name)
        if override is not None and override.allowed_tools is not None:
            # Restriction only — never expand beyond class allow-list.
            return frozenset(override.allowed_tools) & frozenset(agent.allowed_tools)
        return frozenset(agent.allowed_tools)

    def list_all(self) -> list[BaseAgent]:
        return [self._agents[name] for name in sorted(self._agents)]

    def enabled_agents(self) -> list[BaseAgent]:
        return [agent for agent in self.list_all() if self.is_effectively_enabled(agent)]

    def names(self) -> list[str]:
        return sorted(self._agents)

    def resolve_capabilities(self, name: str) -> frozenset[str]:
        agent = self.get(name)
        return frozenset(cap.value for cap in agent.capabilities)

    def require_enabled(self, name: str) -> BaseAgent:
        agent = self.get(name)
        if not self.is_effectively_enabled(agent):
            raise AgentDisabledError(name)
        return agent

    def can_disable(self, name: str) -> bool:
        agent = self.get(name)
        return not (agent.required_for_multi_agent or name in REQUIRED_MULTI_AGENT_KEYS)

    def set_enabled(self, name: str, enabled: bool) -> None:
        agent = self.get(name)
        if not enabled and not self.can_disable(name):
            raise AgentRegistryError(
                f"Agent '{name}' is required for multi-agent mode and cannot be disabled"
            )
        current = self._overrides.get(name) or AgentRuntimeOverride()
        self._overrides[name] = AgentRuntimeOverride(
            enabled=enabled,
            timeout_seconds=current.timeout_seconds,
            maximum_steps=current.maximum_steps,
            allowed_tools=current.allowed_tools,
        )
        _ = agent  # ensure registered

    def to_view(self, agent: BaseAgent) -> AgentDefinitionView:
        return AgentDefinitionView(
            key=agent.name,
            display_name=agent.display_name,
            description=agent.description,
            version=agent.version,
            enabled=self.is_effectively_enabled(agent),
            system_managed=agent.system_managed,
            capabilities=sorted(cap.value for cap in agent.capabilities),
            allowed_tools=sorted(self.effective_allowed_tools(agent)),
            maximum_steps=self.effective_maximum_steps(agent),
            timeout_seconds=self.effective_timeout(agent),
            required_for_multi_agent=agent.required_for_multi_agent
            or agent.name in REQUIRED_MULTI_AGENT_KEYS,
        )

    def list_views(self, *, enabled_only: bool = False) -> list[AgentDefinitionView]:
        agents = self.enabled_agents() if enabled_only else self.list_all()
        return [self.to_view(agent) for agent in agents]

    def validate_plan(
        self,
        plan: AgentPlan,
        *,
        max_tasks: int,
        max_depth: int,
        max_tool_calls: int,
        enabled_tool_names: frozenset[str] | None = None,
    ) -> None:
        """Reject invalid plans before execution. Authoritative server-side check."""
        if not plan.tasks:
            raise AgentPlanValidationError("Plan must include at least one task")
        if len(plan.tasks) > max_tasks:
            raise AgentPlanValidationError(
                f"Plan exceeds maximum task count ({max_tasks})",
                code="agent_plan_too_many_tasks",
            )

        sequences = [task.sequence for task in plan.tasks]
        if len(sequences) != len(set(sequences)):
            raise AgentPlanValidationError(
                "Plan contains duplicate sequence numbers",
                code="agent_plan_duplicate_sequence",
            )

        sequence_set = set(sequences)
        total_tools = 0
        depth_by_seq: dict[int, int] = {}

        for task in sorted(plan.tasks, key=lambda item: item.sequence):
            self._validate_plan_task(
                task,
                sequence_set=sequence_set,
                enabled_tool_names=enabled_tool_names,
            )
            total_tools += len(task.allowed_tools)
            dep_depths = [depth_by_seq[dep] for dep in task.dependencies if dep in depth_by_seq]
            depth = (max(dep_depths) + 1) if dep_depths else 0
            depth_by_seq[task.sequence] = depth
            if depth > max_depth:
                raise AgentPlanValidationError(
                    f"Plan exceeds maximum depth ({max_depth})",
                    code="agent_plan_excessive_depth",
                )

        if total_tools > max_tool_calls:
            raise AgentPlanValidationError(
                f"Plan exceeds maximum tool call budget ({max_tool_calls})",
                code="agent_plan_too_many_tools",
            )

        # Cycle detection via dependency graph.
        self._reject_cycles(plan.tasks)

        try:
            self.require_enabled(plan.final_response_agent)
        except AgentNotFoundError as exc:
            raise AgentPlanValidationError(
                f"Final response agent '{plan.final_response_agent}' is not registered",
                code="agent_plan_invalid_final_agent",
            ) from exc
        except AgentDisabledError as exc:
            raise AgentPlanValidationError(
                f"Final response agent '{plan.final_response_agent}' is disabled",
                code="agent_plan_disabled_final_agent",
            ) from exc

        # Safety and coordinator are never assigned as plan tasks by the planner
        # for user work — but if present they must be registered.
        for task in plan.tasks:
            if task.agent_name not in SYSTEM_AGENT_KEYS and task.agent_name not in self._agents:
                raise AgentPlanValidationError(
                    f"Unknown agent '{task.agent_name}'",
                    code="agent_plan_unknown_agent",
                )

    def _validate_plan_task(
        self,
        task: AgentPlanTask,
        *,
        sequence_set: set[int],
        enabled_tool_names: frozenset[str] | None,
    ) -> None:
        try:
            agent = self.require_enabled(task.agent_name)
        except AgentNotFoundError as exc:
            raise AgentPlanValidationError(
                f"Unknown agent '{task.agent_name}'",
                code="agent_plan_unknown_agent",
            ) from exc
        except AgentDisabledError as exc:
            raise AgentPlanValidationError(
                f"Disabled agent '{task.agent_name}'",
                code="agent_plan_disabled_agent",
            ) from exc

        if not task.objective.strip():
            raise AgentPlanValidationError("Task objective must not be empty")

        for dep in task.dependencies:
            if dep not in sequence_set:
                raise AgentPlanValidationError(
                    f"Task {task.sequence} depends on unknown sequence {dep}",
                    code="agent_plan_invalid_dependency",
                )
            if dep >= task.sequence:
                raise AgentPlanValidationError(
                    f"Task {task.sequence} dependency {dep} must reference an earlier task",
                    code="agent_plan_invalid_dependency",
                )

        allowed = self.effective_allowed_tools(agent)
        for tool_name in task.allowed_tools:
            if tool_name not in allowed:
                raise AgentPlanValidationError(
                    f"Tool '{tool_name}' is not allowed for agent '{task.agent_name}'",
                    code="agent_plan_unauthorized_tool",
                )
            if enabled_tool_names is not None and tool_name not in enabled_tool_names:
                raise AgentPlanValidationError(
                    f"Tool '{tool_name}' is disabled",
                    code="agent_plan_disabled_tool",
                )

    def _reject_cycles(self, tasks: list[AgentPlanTask]) -> None:
        graph: dict[int, list[int]] = {task.sequence: list(task.dependencies) for task in tasks}
        visiting: set[int] = set()
        visited: set[int] = set()

        def dfs(node: int) -> None:
            if node in visiting:
                raise AgentPlanValidationError(
                    "Plan contains a dependency cycle",
                    code="agent_plan_cyclic",
                )
            if node in visited:
                return
            visiting.add(node)
            for dep in graph.get(node, []):
                dfs(dep)
            visiting.remove(node)
            visited.add(node)

        for seq in graph:
            dfs(seq)


def build_agent_registry(agents: Iterable[BaseAgent] | None = None) -> AgentRegistry:
    registry = AgentRegistry()
    if agents is not None:
        for agent in agents:
            registry.register(agent)
    return registry
