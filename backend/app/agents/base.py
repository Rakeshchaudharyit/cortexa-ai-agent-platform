"""Base contract for registered multi-agent specialists."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from app.agents.capabilities import AgentCapability
from app.agents.context import AgentContextEnvelope
from app.agents.schemas import AgentTaskRequest, AgentTaskResult


@dataclass(frozen=True)
class AgentMeta:
    """Immutable metadata for a registered agent."""

    name: str
    version: str
    description: str
    display_name: str
    capabilities: frozenset[AgentCapability]
    allowed_tools: frozenset[str]
    maximum_steps: int
    timeout_seconds: int
    system_managed: bool = True
    required_for_multi_agent: bool = False


@dataclass
class AgentRuntimeOverride:
    """Admin/runtime override for a registered agent (does not mutate ClassVars)."""

    enabled: bool | None = None
    timeout_seconds: int | None = None
    maximum_steps: int | None = None
    allowed_tools: frozenset[str] | None = None


class BaseAgent(ABC):
    """Server-side specialist agent. Names and tools are never model-supplied."""

    name: ClassVar[str]
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str]
    display_name: ClassVar[str]
    capabilities: ClassVar[frozenset[AgentCapability]]
    allowed_tools: ClassVar[frozenset[str]] = frozenset()
    maximum_steps: ClassVar[int] = 4
    timeout_seconds: ClassVar[int] = 45
    enabled: ClassVar[bool] = True
    system_managed: ClassVar[bool] = True
    required_for_multi_agent: ClassVar[bool] = False

    def meta(self) -> AgentMeta:
        return AgentMeta(
            name=self.name,
            version=self.version,
            description=self.description,
            display_name=self.display_name,
            capabilities=self.capabilities,
            allowed_tools=self.allowed_tools,
            maximum_steps=self.maximum_steps,
            timeout_seconds=self.timeout_seconds,
            system_managed=self.system_managed,
            required_for_multi_agent=self.required_for_multi_agent,
        )

    def can_handle(self, task: AgentTaskRequest) -> bool:
        """Return True when this agent is appropriate for the task type."""
        return task.agent_name == self.name

    def validate_task(self, task: AgentTaskRequest) -> None:
        """Raise AgentPlanValidationError when the task is invalid for this agent."""
        if task.agent_name != self.name:
            from app.agents.exceptions import AgentPlanValidationError

            raise AgentPlanValidationError(
                f"Task assigned to '{task.agent_name}' cannot be executed by '{self.name}'"
            )

    def build_context(
        self,
        envelope: AgentContextEnvelope,
        *,
        task: AgentTaskRequest,
    ) -> AgentContextEnvelope:
        """Return a filtered context envelope for this agent (default: pass-through)."""
        _ = task
        return envelope

    @abstractmethod
    async def execute(
        self,
        *,
        task: AgentTaskRequest,
        context: AgentContextEnvelope,
        **kwargs: Any,
    ) -> AgentTaskResult:
        """Execute a validated task with bounded context."""
