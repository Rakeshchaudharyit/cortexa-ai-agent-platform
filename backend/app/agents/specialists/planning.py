"""Planning Agent — structured plans from registered agents only."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from app.agents.base import BaseAgent
from app.agents.capabilities import AgentCapability
from app.agents.context import AgentContextEnvelope
from app.agents.exceptions import AgentPlanValidationError
from app.agents.registry import AgentRegistry
from app.agents.schemas import (
    AgentComplexityDecision,
    AgentPlan,
    AgentPlanTask,
    AgentTaskRequest,
    AgentTaskResult,
)
from app.agents.specialists.common import load_json_object, truncate_output
from app.core.config import Settings
from app.llm.schemas import ChatMessage, GenerateRequest, MessageRole

logger = logging.getLogger("cortexa.agents.planning")


class PlanningSpecialist(BaseAgent):
    """Decompose complex requests into validated AgentPlan structures."""

    name: ClassVar[str] = "planning"
    display_name: ClassVar[str] = "Planning Agent"
    description: ClassVar[str] = (
        "Decomposes complex requests into structured task plans using "
        "registered agent names only. Never executes tools or writes data."
    )
    capabilities: ClassVar[frozenset[AgentCapability]] = frozenset(
        {
            AgentCapability.decompose,
            AgentCapability.structure_plan,
            AgentCapability.identify_approvals,
        }
    )
    allowed_tools: ClassVar[frozenset[str]] = frozenset()
    maximum_steps: ClassVar[int] = 2
    timeout_seconds: ClassVar[int] = 45

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        registry: AgentRegistry | None = None,
        llm_service: Any | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.llm_service = llm_service

    async def execute(
        self,
        *,
        task: AgentTaskRequest,
        context: AgentContextEnvelope,
        **kwargs: Any,
    ) -> AgentTaskResult:
        decision = kwargs.get("classifier_decision")
        enabled_tools = kwargs.get("enabled_tool_names")
        plan = await self.create_plan(
            user_request=context.user_request,
            decision=decision
            if isinstance(decision, AgentComplexityDecision)
            else AgentComplexityDecision(
                execution_mode="multi_agent",
                confidence=0.8,
                reason_codes=["planning_fallback"],
                suggested_agents=["knowledge", "conversation"],
                requires_planning=True,
                safe_summary="Planning from task objective",
            ),
            enabled_tool_names=frozenset(enabled_tools or context.allowed_tools or []),
            selected_document_ids=[str(d) for d in context.allowed_document_ids],
            memory_enabled=bool(context.memory_context)
            or bool((context.execution_metadata or {}).get("memory_enabled")),
        )
        return AgentTaskResult(
            success=True,
            agent_name=self.name,
            task_type=task.task_type,
            result_summary=truncate_output(plan.reasoning_summary, 500),
            output={"plan": plan.model_dump()},
            llm_calls_used=1 if kwargs.get("_used_llm") else 0,
        )

    async def create_plan(
        self,
        *,
        user_request: str,
        decision: AgentComplexityDecision,
        enabled_tool_names: frozenset[str] | None = None,
        selected_document_ids: list[str] | None = None,
        memory_enabled: bool = False,
        allowed_agents: frozenset[str] | None = None,
    ) -> AgentPlan:
        """Build a plan via deterministic templates, with optional LLM assist."""
        settings = self.settings
        registry = self.registry
        if settings is None or registry is None:
            raise AgentPlanValidationError("Planning agent is not configured")

        template = self._template_plan(
            user_request=user_request,
            decision=decision,
            enabled_tool_names=enabled_tool_names or frozenset(),
            selected_document_ids=selected_document_ids or [],
            memory_enabled=memory_enabled,
        )
        if template is not None:
            self._validate(template, enabled_tool_names=enabled_tool_names)
            return template

        max_replans = settings.agent_max_replans
        last_error: Exception | None = None
        for attempt in range(max_replans + 1):
            try:
                plan = await self._plan_with_model(
                    user_request=user_request,
                    decision=decision,
                    enabled_tool_names=enabled_tool_names or frozenset(),
                    allowed_agents=allowed_agents,
                )
                self._validate(plan, enabled_tool_names=enabled_tool_names)
                return plan
            except (AgentPlanValidationError, ValueError) as exc:
                last_error = exc
                logger.info(
                    "planning_replan attempt=%s error_code=%s",
                    attempt,
                    getattr(exc, "code", type(exc).__name__),
                )
                if attempt >= max_replans:
                    break

        # Safe fallback: conversation-only plan when model planning fails.
        fallback = AgentPlan(
            goal=truncate_output(user_request, 500),
            requires_multi_agent=False,
            reasoning_summary="Falling back to a single conversation response.",
            tasks=[
                AgentPlanTask(
                    sequence=1,
                    agent_name="conversation",
                    task_type="respond",
                    objective=truncate_output(user_request, 500),
                    expected_output="User-facing answer",
                )
            ],
            final_response_agent="conversation",
            estimated_steps=1,
            requires_approval=decision.requires_approval,
        )
        if last_error is not None and settings.multi_agent_enabled:
            # Policy: when multi-agent was required, surface a safe error via validation
            # only if conversation agent itself is disabled; else allow fallback.
            try:
                self._validate(fallback, enabled_tool_names=enabled_tool_names)
            except AgentPlanValidationError:
                raise last_error from last_error
        return fallback

    def _validate(
        self,
        plan: AgentPlan,
        *,
        enabled_tool_names: frozenset[str] | None,
    ) -> None:
        assert self.settings is not None and self.registry is not None
        self.registry.validate_plan(
            plan,
            max_tasks=self.settings.agent_max_tasks,
            max_depth=self.settings.agent_max_depth,
            max_tool_calls=self.settings.agent_max_tool_calls,
            enabled_tool_names=enabled_tool_names,
        )

    def _template_plan(
        self,
        *,
        user_request: str,
        decision: AgentComplexityDecision,
        enabled_tool_names: frozenset[str],
        selected_document_ids: list[str],
        memory_enabled: bool,
    ) -> AgentPlan | None:
        codes = set(decision.reason_codes)
        suggested = set(decision.suggested_agents)
        goal = truncate_output(user_request, 500)
        has_knowledge = "knowledge" in suggested or bool(selected_document_ids)
        has_tool = "tool" in suggested or any(
            c.startswith("capability_calculator")
            or c.startswith("capability_datetime")
            or c.startswith("combo_knowledge_tool")
            or c.startswith("combo_document_calc")
            for c in codes
        )
        has_memory = "memory" in suggested or any("memory" in c for c in codes)
        needs_memory_write = decision.requires_approval or "capability_memory_write" in codes

        # knowledge + tool + conversation
        if has_knowledge and has_tool and not (has_memory and needs_memory_write):
            tools = [t for t in ("calculator", "current_datetime") if t in enabled_tool_names]
            if not tools and "calculator" in enabled_tool_names:
                tools = ["calculator"]
            tasks = [
                AgentPlanTask(
                    sequence=1,
                    agent_name="knowledge",
                    task_type="retrieve",
                    objective="Retrieve relevant facts from the selected documents",
                    expected_output="Bounded facts and citations",
                ),
                AgentPlanTask(
                    sequence=2,
                    agent_name="tool",
                    task_type="compute",
                    objective="Perform the required calculation or datetime lookup",
                    dependencies=[1],
                    allowed_tools=tools[:2],
                    expected_output="Structured tool result",
                ),
                AgentPlanTask(
                    sequence=3,
                    agent_name="conversation",
                    task_type="synthesize",
                    objective=(
                        "Synthesize a final recommendation from retrieved facts " "and tool results"
                    ),
                    dependencies=[1, 2],
                    expected_output="User-facing answer with citations",
                ),
            ]
            return AgentPlan(
                goal=goal,
                reasoning_summary=(
                    "This request needs document review, a calculation, and final synthesis."
                ),
                tasks=tasks,
                estimated_steps=3,
            )

        # memory + knowledge + conversation
        if has_knowledge and has_memory and not has_tool:
            tasks = [
                AgentPlanTask(
                    sequence=1,
                    agent_name="memory",
                    task_type="retrieve_memories",
                    objective="Retrieve approved relevant memories",
                    expected_output="Bounded memory summaries",
                ),
                AgentPlanTask(
                    sequence=2,
                    agent_name="knowledge",
                    task_type="retrieve",
                    objective="Retrieve relevant facts from the selected documents",
                    expected_output="Bounded facts and citations",
                ),
                AgentPlanTask(
                    sequence=3,
                    agent_name="conversation",
                    task_type="synthesize",
                    objective="Draft a response using memories and document facts",
                    dependencies=[1, 2],
                    expected_output="User-facing synthesized answer",
                ),
            ]
            if needs_memory_write:
                tasks.insert(
                    3,
                    AgentPlanTask(
                        sequence=4,
                        agent_name="memory",
                        task_type="propose_write",
                        objective="Propose remembering the final decision (approval required)",
                        dependencies=[3],
                        requires_approval=True,
                        expected_output="Approval-required memory proposal",
                    ),
                )
                # Fix synthesize as final when write is appended — keep conversation last.
                tasks = [
                    AgentPlanTask(
                        sequence=1,
                        agent_name="memory",
                        task_type="retrieve_memories",
                        objective="Retrieve approved relevant memories",
                        expected_output="Bounded memory summaries",
                    ),
                    AgentPlanTask(
                        sequence=2,
                        agent_name="knowledge",
                        task_type="retrieve",
                        objective="Retrieve relevant facts from the selected documents",
                        expected_output="Bounded facts and citations",
                    ),
                    AgentPlanTask(
                        sequence=3,
                        agent_name="memory",
                        task_type="propose_write",
                        objective="Propose remembering the final decision (approval required)",
                        dependencies=[1, 2],
                        requires_approval=True,
                        expected_output="Approval-required memory proposal",
                    ),
                    AgentPlanTask(
                        sequence=4,
                        agent_name="conversation",
                        task_type="synthesize",
                        objective="Draft a revised proposal using memories and document facts",
                        dependencies=[1, 2, 3],
                        expected_output="User-facing synthesized answer",
                    ),
                ]
            return AgentPlan(
                goal=goal,
                reasoning_summary=(
                    "This request needs saved preferences, document context, and synthesis."
                    if memory_enabled
                    else "This request needs document context and synthesis."
                ),
                tasks=tasks,
                estimated_steps=len(tasks),
                requires_approval=needs_memory_write,
            )

        # knowledge + tool + memory proposal + conversation
        if has_knowledge and has_tool and has_memory:
            tools = [t for t in ("calculator", "current_datetime") if t in enabled_tool_names]
            tasks = [
                AgentPlanTask(
                    sequence=1,
                    agent_name="memory",
                    task_type="retrieve_memories",
                    objective="Retrieve approved relevant memories",
                    expected_output="Bounded memory summaries",
                ),
                AgentPlanTask(
                    sequence=2,
                    agent_name="knowledge",
                    task_type="retrieve",
                    objective="Retrieve relevant facts from the selected documents",
                    expected_output="Bounded facts and citations",
                ),
                AgentPlanTask(
                    sequence=3,
                    agent_name="tool",
                    task_type="compute",
                    objective="Perform the required calculation",
                    dependencies=[2],
                    allowed_tools=tools[:2] or ["calculator"],
                    expected_output="Structured tool result",
                ),
                AgentPlanTask(
                    sequence=4,
                    agent_name="memory",
                    task_type="propose_write",
                    objective="Propose remembering the final decision (approval required)",
                    dependencies=[1, 2, 3],
                    requires_approval=True,
                    expected_output="Approval-required memory proposal",
                ),
                AgentPlanTask(
                    sequence=5,
                    agent_name="conversation",
                    task_type="synthesize",
                    objective="Synthesize the final user-facing recommendation",
                    dependencies=[1, 2, 3, 4],
                    expected_output="User-facing answer",
                ),
            ]
            return AgentPlan(
                goal=goal,
                reasoning_summary=(
                    "This request needs memories, document review, a calculation, "
                    "and final synthesis."
                ),
                tasks=tasks,
                estimated_steps=5,
                requires_approval=True,
            )

        # knowledge + conversation only (multi when recommend was classified)
        if has_knowledge and "combo_knowledge_recommend" in codes:
            return AgentPlan(
                goal=goal,
                reasoning_summary="This request needs document review and final synthesis.",
                tasks=[
                    AgentPlanTask(
                        sequence=1,
                        agent_name="knowledge",
                        task_type="retrieve",
                        objective="Retrieve and summarize relevant document facts",
                        expected_output="Bounded facts and citations",
                    ),
                    AgentPlanTask(
                        sequence=2,
                        agent_name="conversation",
                        task_type="synthesize",
                        objective="Prepare a recommendation from retrieved facts",
                        dependencies=[1],
                        expected_output="User-facing recommendation",
                    ),
                ],
                estimated_steps=2,
            )

        return None

    async def _plan_with_model(
        self,
        *,
        user_request: str,
        decision: AgentComplexityDecision,
        enabled_tool_names: frozenset[str],
        allowed_agents: frozenset[str] | None,
    ) -> AgentPlan:
        if self.llm_service is None:
            raise AgentPlanValidationError(
                "No planning template matched and LLM planning is unavailable",
                code="agent_plan_unavailable",
            )
        assert self.registry is not None and self.settings is not None
        enabled = [a.name for a in self.registry.enabled_agents()]
        if allowed_agents is not None:
            enabled = [n for n in enabled if n in allowed_agents]
        # Never ask the model to schedule coordinator/safety as work tasks.
        enabled = [n for n in enabled if n not in {"coordinator", "safety", "planning"}]
        prompt = (
            "Create a multi-agent plan as JSON with keys: goal, reasoning_summary, "
            "tasks (array of {sequence, agent_name, task_type, objective, dependencies, "
            "allowed_tools, expected_output, requires_approval}), final_response_agent, "
            "estimated_steps, requires_approval. "
            "Use only these agents: "
            f"{enabled}. Allowed tools: {sorted(enabled_tool_names)}. "
            "Final response agent must be conversation. "
            "reasoning_summary must be a short user-safe sentence, never chain-of-thought.\n"
            f"User request: {user_request[:1500]}\n"
            f"Classifier: {decision.reason_codes}"
        )
        response = await self.llm_service.generate(
            GenerateRequest(
                messages=[
                    ChatMessage(
                        role=MessageRole.system,
                        content=(
                            "You are the Planning Agent. Output JSON only. "
                            "Never execute tools. Never invent agent or tool names."
                        ),
                    ),
                    ChatMessage(role=MessageRole.user, content=prompt),
                ],
                temperature=0.0,
                max_tokens=256,
            )
        )
        data = load_json_object(response.content or "")
        if not data:
            raise AgentPlanValidationError(
                "Malformed model plan",
                code="agent_plan_malformed",
            )
        # Strip forbidden hidden-reasoning fields if the model emits them.
        data.pop("reasoning", None)
        data.pop("chain_of_thought", None)
        data.pop("hidden_reasoning", None)
        try:
            return AgentPlan.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            raise AgentPlanValidationError(
                "Malformed model plan schema",
                code="agent_plan_malformed",
            ) from exc
