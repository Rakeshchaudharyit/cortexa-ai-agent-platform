"""System-managed specialist agent definitions (server-registered only)."""

from __future__ import annotations

from typing import Any, ClassVar

from app.agents.base import BaseAgent
from app.agents.capabilities import AgentCapability
from app.agents.context import AgentContextEnvelope
from app.agents.registry import AgentRegistry, build_agent_registry
from app.agents.schemas import AgentTaskRequest, AgentTaskResult
from app.agents.specialists.conversation import ConversationSpecialist
from app.agents.specialists.knowledge import KnowledgeSpecialist
from app.agents.specialists.memory import MemorySpecialist
from app.agents.specialists.planning import PlanningSpecialist
from app.agents.specialists.safety import SafetySpecialist
from app.agents.specialists.tool_agent import ToolSpecialist

# Re-export specialist class names expected by Phase 9.1 registry tests / imports.
PlanningAgent = PlanningSpecialist
ConversationAgent = ConversationSpecialist
KnowledgeAgent = KnowledgeSpecialist
MemoryAgentDef = MemorySpecialist
ToolAgent = ToolSpecialist
SafetyAgent = SafetySpecialist


class CoordinatorAgent(BaseAgent):
    """Registry entry for the coordinator. Execution lives in CoordinatorEngine."""

    name: ClassVar[str] = "coordinator"
    display_name: ClassVar[str] = "Coordinator Agent"
    description: ClassVar[str] = (
        "Owns each execution: classifies complexity, validates plans, "
        "dispatches tasks, enforces limits, and produces the final response."
    )
    capabilities: ClassVar[frozenset[AgentCapability]] = frozenset(
        {
            AgentCapability.classify,
            AgentCapability.dispatch,
            AgentCapability.enforce_limits,
            AgentCapability.combine_results,
            AgentCapability.cancel,
        }
    )
    allowed_tools: ClassVar[frozenset[str]] = frozenset()
    maximum_steps: ClassVar[int] = 12
    timeout_seconds: ClassVar[int] = 120
    required_for_multi_agent: ClassVar[bool] = True

    async def execute(
        self,
        *,
        task: AgentTaskRequest,
        context: AgentContextEnvelope,
        **kwargs: Any,
    ) -> AgentTaskResult:
        _ = (task, context, kwargs)
        return AgentTaskResult(
            success=True,
            agent_name=self.name,
            task_type=task.task_type,
            result_summary="Coordinator acknowledged task",
        )


def create_system_agents() -> list[BaseAgent]:
    return [
        CoordinatorAgent(),
        PlanningSpecialist(),
        ConversationSpecialist(),
        KnowledgeSpecialist(),
        MemorySpecialist(),
        ToolSpecialist(),
        SafetySpecialist(),
    ]


def create_default_agent_registry() -> AgentRegistry:
    return build_agent_registry(create_system_agents())
