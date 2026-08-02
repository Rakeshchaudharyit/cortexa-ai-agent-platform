"""Coordinator engine — classify, plan, safety-check, and execute multi-agent runs."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.budgets import RunBudget
from app.agents.classifier import ComplexityClassifier
from app.agents.context import AgentContextEnvelope, AgentContextLimits
from app.agents.exceptions import (
    AgentCancelledError,
    AgentError,
    AgentLimitExceededError,
    AgentPlanValidationError,
    AgentSafetyError,
    AgentStateTransitionError,
    AgentTimeoutError,
)
from app.agents.registry import AgentRegistry
from app.agents.repository import AgentRunRepository
from app.agents.schemas import (
    AgentComplexityDecision,
    AgentExecutionResult,
    AgentPlan,
    AgentPlanTask,
    AgentTaskRequest,
    AgentTaskResult,
    ClassifierInput,
    SafetyDecision,
)
from app.agents.specialists.conversation import ConversationSpecialist
from app.agents.specialists.knowledge import KnowledgeSpecialist
from app.agents.specialists.memory import MemorySpecialist
from app.agents.specialists.planning import PlanningSpecialist
from app.agents.specialists.safety import SafetySpecialist
from app.agents.specialists.tool_agent import ToolSpecialist
from app.core.config import Settings
from app.models.agent import AgentRun, AgentTask
from app.models.enums import AgentExecutionMode, AgentRunStatus, AgentTaskStatus
from app.models.user import User

logger = logging.getLogger("cortexa.agents.coordinator")


_RETRYABLE_CODES = frozenset(
    {
        "llm_request_timeout",
        "LLMRequestTimeoutError",
        "TimeoutError",
        "knowledge_retrieval_failed",
        "memory_retrieval_failed",
        "tool_timeout",
        "provider_unavailable",
        "LLMProviderUnavailableError",
        "LLMModelUnavailableError",
    }
)


@dataclass
class CoordinatorRequest:
    """Authenticated execution request for the coordinator."""

    user: User
    user_message: str
    conversation_id: UUID | None = None
    conversation_mode: str = "general"
    selected_document_ids: list[UUID] = field(default_factory=list)
    memory_enabled: bool = False
    explicit_memory_intent: bool = False
    selected_tool_intent: list[str] = field(default_factory=list)
    conversation_summary: str | None = None
    selected_history: list[dict[str, str]] = field(default_factory=list)
    memory_context: list[dict[str, Any]] = field(default_factory=list)
    document_context: list[dict[str, Any]] = field(default_factory=list)
    correlation_id: str = ""
    enabled_tool_names: frozenset[str] = field(default_factory=frozenset)
    cancel_check: Any | None = None
    on_run_created: Any | None = None
    event_callback: Any | None = None


@dataclass
class CoordinatorResult:
    """Outcome of coordinator execution (internal — not a public API)."""

    execution_mode: str
    used_single_agent_fallback: bool
    run: AgentRun | None = None
    decision: AgentComplexityDecision | None = None
    plan: AgentPlan | None = None
    safety: SafetyDecision | None = None
    final_content: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    task_results: list[dict[str, Any]] = field(default_factory=list)
    error_code: str | None = None
    safe_error_message: str | None = None
    approval_required: bool = False


class CoordinatorEngine:
    """Owns multi-agent classification, planning, safety, and sequential task execution."""

    def __init__(
        self,
        *,
        settings: Settings,
        registry: AgentRegistry,
        repository: AgentRunRepository,
        classifier: ComplexityClassifier | None = None,
        llm_service: Any | None = None,
        retrieval_service: Any | None = None,
        memory_service: Any | None = None,
        memory_retriever: Any | None = None,
        tool_executor: Any | None = None,
        tool_registry: Any | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.repository = repository
        self.llm_service = llm_service
        self.classifier = classifier or ComplexityClassifier(settings, llm_service=llm_service)
        self.planning = PlanningSpecialist(
            settings=settings, registry=registry, llm_service=llm_service
        )
        self.safety = SafetySpecialist(
            settings=settings, registry=registry, llm_service=llm_service
        )
        self.conversation = ConversationSpecialist(settings=settings, llm_service=llm_service)
        self.knowledge = KnowledgeSpecialist(settings=settings, retrieval_service=retrieval_service)
        self.memory = MemorySpecialist(
            settings=settings,
            memory_service=memory_service,
            memory_retriever=memory_retriever,
        )
        self.tool = ToolSpecialist(
            settings=settings,
            tool_executor=tool_executor,
            tool_registry=tool_registry,
        )
        # Ensure registry agents are the wired specialists when present.
        self._wire_registry_agents()

    def _wire_registry_agents(self) -> None:
        """Replace stub registry instances with service-wired specialists when names match."""
        for agent in (
            self.planning,
            self.safety,
            self.conversation,
            self.knowledge,
            self.memory,
            self.tool,
        ):
            if self.registry.has(agent.name):
                self.registry.unregister(agent.name)
            self.registry.register(agent)

    async def execute(
        self,
        session: AsyncSession,
        request: CoordinatorRequest,
    ) -> CoordinatorResult:
        correlation_id = request.correlation_id or str(uuid.uuid4())
        decision = await self.classifier.classify(
            ClassifierInput(
                user_message=request.user_message,
                conversation_mode=request.conversation_mode,
                selected_document_ids=[str(d) for d in request.selected_document_ids],
                memory_enabled=request.memory_enabled,
                explicit_memory_intent=request.explicit_memory_intent,
                selected_tool_intent=list(request.selected_tool_intent),
                conversation_context_summary=request.conversation_summary,
                enabled_feature_flags={"multi_agent_enabled": self.settings.multi_agent_enabled},
            )
        )

        if (
            not self.settings.multi_agent_enabled
            or decision.execution_mode == "single_agent"
            or not decision.requires_planning
        ):
            logger.info(
                "coordinator_single_agent_fallback correlation_id=%s "
                "execution_mode=single_agent reason_codes=%s",
                correlation_id,
                ",".join(decision.reason_codes[:8]),
            )
            return CoordinatorResult(
                execution_mode="single_agent",
                used_single_agent_fallback=True,
                decision=decision,
            )

        return await self._execute_multi_agent(session, request, decision, correlation_id)

    async def _execute_multi_agent(
        self,
        session: AsyncSession,
        request: CoordinatorRequest,
        decision: AgentComplexityDecision,
        correlation_id: str,
    ) -> CoordinatorResult:
        run = await self.repository.create_run(
            session,
            user=request.user,
            conversation_id=request.conversation_id,
            original_request=request.user_message,
            correlation_id=correlation_id,
            execution_mode=AgentExecutionMode.multi_agent,
            maximum_steps=self.settings.agent_max_steps,
        )
        if request.on_run_created is not None:
            registered = request.on_run_created(run.id)
            if asyncio.iscoroutine(registered):
                await registered
        await self._add_event(
            request,
            session,
            run=run,
            event_type="run_started",
            agent_key="coordinator",
            safe_metadata={"execution_mode": "multi_agent"},
        )
        await self._add_event(
            request,
            session,
            run=run,
            event_type="complexity_classified",
            agent_key="coordinator",
            safe_metadata={
                "execution_mode": decision.execution_mode,
                "reason_codes": decision.reason_codes[:12],
                "confidence": decision.confidence,
            },
        )

        budget = RunBudget(
            maximum_steps=run.maximum_steps or self.settings.agent_max_steps,
            max_llm_calls=self.settings.agent_max_llm_calls,
            max_tool_calls=self.settings.agent_max_tool_calls,
            max_context_characters=self.settings.agent_context_max_characters,
            run_timeout_seconds=float(self.settings.agent_run_timeout_seconds),
        )

        try:
            await self._raise_if_cancelled(request)
            await self.repository.transition_run(session, run, AgentRunStatus.planning)
            await self._add_event(
                request,
                session,
                run=run,
                event_type="planning_started",
                agent_key="planning",
            )
            await self.repository.add_handoff(
                session,
                run=run,
                from_agent_key="coordinator",
                to_agent_key="planning",
                reason="Create structured plan",
                safe_context_summary=decision.safe_summary,
            )

            plan = await self.planning.create_plan(
                user_request=request.user_message,
                decision=decision,
                enabled_tool_names=request.enabled_tool_names,
                selected_document_ids=[str(d) for d in request.selected_document_ids],
                memory_enabled=request.memory_enabled,
            )
            await self.repository.transition_run(
                session,
                run,
                AgentRunStatus.running,
                safe_plan_summary=plan.reasoning_summary,
            )
            await self._add_event(
                request,
                session,
                run=run,
                event_type="plan_created",
                agent_key="planning",
                safe_metadata={
                    "task_count": len(plan.tasks),
                    "final_response_agent": plan.final_response_agent,
                    "requires_approval": plan.requires_approval,
                },
            )

            await self.repository.add_handoff(
                session,
                run=run,
                from_agent_key="planning",
                to_agent_key="safety",
                reason="Safety review",
                safe_context_summary=plan.reasoning_summary,
            )
            safety = await self.safety.review_plan(
                plan,
                user_request=request.user_message,
                enabled_tool_names=request.enabled_tool_names,
            )
            await self._add_event(
                request,
                session,
                run=run,
                event_type="safety_checked",
                agent_key="safety",
                safe_metadata={
                    "allowed": safety.allowed,
                    "blocked": safety.blocked,
                    "requires_approval": safety.requires_approval,
                    "reason_codes": safety.reason_codes[:12],
                },
            )
            if safety.blocked:
                raise AgentSafetyError(safety.safe_message or "Plan blocked by safety policy")

            tasks = await self.repository.create_tasks_from_plan(
                session,
                run,
                [
                    {
                        "assigned_agent_key": t.agent_name,
                        "task_type": t.task_type,
                        "objective": t.objective,
                        "safe_input_summary": t.expected_output,
                        "sequence": t.sequence,
                        "depth": self._task_depth(t, plan.tasks),
                        "dependencies_json": list(t.dependencies),
                        "allowed_tools_json": list(t.allowed_tools),
                        "requires_approval": t.requires_approval,
                        "maximum_retries": t.maximum_retries,
                    }
                    for t in plan.tasks
                ],
            )

            envelope = self._build_envelope(request, correlation_id)
            budget.observe_context(envelope.character_count())

            task_by_seq = {t.sequence: t for t in tasks}
            results_by_seq: dict[int, dict[str, Any]] = {}
            last_agent = "safety"
            approval_required = safety.requires_approval

            for task in sorted(tasks, key=lambda item: item.sequence):
                await self._raise_if_cancelled(request)
                budget.check_run_timeout()

                deps = list(task.dependencies_json or [])
                dep_failed = False
                for dep_seq in deps:
                    dep_result = results_by_seq.get(int(dep_seq))
                    dep_task = task_by_seq.get(int(dep_seq))
                    if dep_task is None or dep_result is None:
                        dep_failed = True
                        break
                    if dep_task.status in {
                        AgentTaskStatus.failed,
                        AgentTaskStatus.skipped,
                        AgentTaskStatus.cancelled,
                        AgentTaskStatus.timed_out,
                    }:
                        dep_failed = True
                        break
                    if (
                        not dep_result.get("success", False)
                        and dep_task.status != AgentTaskStatus.awaiting_approval
                    ):
                        # approval_required still counts as a usable soft dependency
                        if not dep_result.get("requires_approval"):
                            dep_failed = True
                            break

                if dep_failed:
                    await self.repository.transition_task(
                        session,
                        task,
                        AgentTaskStatus.skipped,
                        result_summary="Skipped because a dependency did not succeed",
                        error_code="dependency_failed",
                        safe_error_message="A required prior task did not succeed",
                    )
                    await self._add_event(
                        request,
                        session,
                        run=run,
                        event_type="task_skipped",
                        agent_key=task.assigned_agent_key,
                        task_id=task.id,
                        safe_metadata={"sequence": task.sequence, "reason": "dependency_failed"},
                    )
                    results_by_seq[task.sequence] = {
                        "success": False,
                        "skipped": True,
                        "agent_name": task.assigned_agent_key,
                        "result_summary": "Skipped because a dependency did not succeed",
                    }
                    continue

                await self.repository.transition_task(session, task, AgentTaskStatus.ready)
                await self._add_event(
                    request,
                    session,
                    run=run,
                    event_type="task_ready",
                    agent_key=task.assigned_agent_key,
                    task_id=task.id,
                    safe_metadata={"sequence": task.sequence},
                )

                if task.assigned_agent_key != last_agent:
                    await self.repository.add_handoff(
                        session,
                        run=run,
                        from_agent_key=last_agent,
                        to_agent_key=task.assigned_agent_key,
                        reason=f"Execute {task.task_type}",
                        task_id=task.id,
                        safe_context_summary=task.objective[:300],
                    )
                    await self._add_event(
                        request,
                        session,
                        run=run,
                        event_type="handoff",
                        agent_key=task.assigned_agent_key,
                        task_id=task.id,
                        safe_metadata={
                            "from": last_agent,
                            "to": task.assigned_agent_key,
                        },
                    )
                    last_agent = task.assigned_agent_key

                prior = [
                    results_by_seq[seq]
                    for seq in sorted(results_by_seq)
                    if results_by_seq[seq].get("success")
                    or results_by_seq[seq].get("requires_approval")
                ]
                task_envelope = envelope.model_copy(
                    update={
                        "prior_task_results": prior,
                        "allowed_tools": list(task.allowed_tools_json or []),
                        "execution_metadata": {
                            **envelope.execution_metadata,
                            "run_id": str(run.id),
                            "task_id": str(task.id),
                        },
                    }
                ).enforce_budgets()
                budget.observe_context(task_envelope.character_count())

                result = await self._run_task_with_retries(
                    session,
                    request=request,
                    run=run,
                    task=task,
                    envelope=task_envelope,
                    budget=budget,
                )
                results_by_seq[task.sequence] = result
                if result.get("requires_approval"):
                    approval_required = True
                    approval_action_type = str(
                        result.get("approval_action_type") or "sensitive_action"
                    )
                    # Keep the write payload internal to the task record. Public
                    # serializers never expose this field.
                    task.safe_input_summary = str(result.get("approval_summary") or task.objective)[
                        :500
                    ]
                    await self.repository.create_approval(
                        session,
                        run=run,
                        task=task,
                        user=request.user,
                        action_type=str(result.get("approval_action_type") or "sensitive_action"),
                        safe_action_summary=(
                            "Confirm " f"{approval_action_type.replace('_', ' ')} " "action"
                        )[:500],
                    )
                    await self.repository.transition_task(
                        session, task, AgentTaskStatus.awaiting_approval
                    )
                    await self.repository.transition_run(
                        session, run, AgentRunStatus.awaiting_approval
                    )
                    await self._add_event(
                        request,
                        session,
                        run=run,
                        event_type="approval_required",
                        agent_key=task.assigned_agent_key,
                        task_id=task.id,
                        safe_metadata={"action_type": result.get("approval_action_type")},
                    )
                    # Approval is a durable pause. No dependent work starts until
                    # an owned approval endpoint resolves this gate.
                    run.steps_used = budget.steps_used
                    run.llm_calls_used = budget.llm_calls_used
                    run.tool_calls_used = budget.tool_calls_used
                    return CoordinatorResult(
                        execution_mode="multi_agent",
                        used_single_agent_fallback=False,
                        run=run,
                        decision=decision,
                        plan=plan,
                        safety=safety,
                        task_results=[results_by_seq[s] for s in sorted(results_by_seq)],
                        approval_required=True,
                    )

            # Collect final synthesis content from conversation task if present.
            final_content = ""
            citations: list[dict[str, Any]] = []
            ordered_results = [results_by_seq[s] for s in sorted(results_by_seq)]
            for item in ordered_results:
                if item.get("agent_name") == "conversation" and item.get("content"):
                    final_content = str(item["content"])
                for cite in item.get("citations") or []:
                    if isinstance(cite, dict):
                        citations.append(cite)

            if not final_content:
                # Ensure a conversation synthesis if plan omitted it but we have priors.
                synth = await self._synthesize_fallback(
                    session, request, run, envelope, ordered_results, budget
                )
                final_content = synth.get("content") or ""
                citations.extend(synth.get("citations") or [])

            run.steps_used = budget.steps_used
            run.llm_calls_used = budget.llm_calls_used
            run.tool_calls_used = budget.tool_calls_used
            await self.repository.transition_run(session, run, AgentRunStatus.completed)
            await self._add_event(
                request,
                session,
                run=run,
                event_type="run_completed",
                agent_key="coordinator",
                safe_metadata=dict(budget.snapshot()),
            )
            logger.info(
                "coordinator_run_completed run_id=%s correlation_id=%s "
                "plan_task_count=%s steps_used=%s llm_calls_used=%s tool_calls_used=%s "
                "duration_ms=%s",
                run.id,
                correlation_id,
                len(plan.tasks),
                budget.steps_used,
                budget.llm_calls_used,
                budget.tool_calls_used,
                budget.duration_ms,
            )
            return CoordinatorResult(
                execution_mode="multi_agent",
                used_single_agent_fallback=False,
                run=run,
                decision=decision,
                plan=plan,
                safety=safety,
                final_content=final_content,
                citations=citations,
                task_results=ordered_results,
                approval_required=approval_required,
            )
        except AgentTimeoutError as exc:
            return await self._fail_run(
                session, request, run, budget, decision, "run_timed_out", exc.code, str(exc)
            )
        except AgentCancelledError as exc:
            await self.repository.cancel_queued_tasks(session, run)
            return await self._fail_run(
                session,
                request,
                run,
                budget,
                decision,
                "run_failed",
                exc.code,
                str(exc),
                status=AgentRunStatus.cancelled,
            )
        except (AgentSafetyError, AgentPlanValidationError, AgentLimitExceededError) as exc:
            return await self._fail_run(
                session, request, run, budget, decision, "run_failed", exc.code, str(exc)
            )
        except AgentError as exc:
            return await self._fail_run(
                session, request, run, budget, decision, "run_failed", exc.code, str(exc)
            )
        except Exception:  # noqa: BLE001
            logger.exception("coordinator_unexpected_failure correlation_id=%s", correlation_id)
            return await self._fail_run(
                session,
                request,
                run,
                budget,
                decision,
                "run_failed",
                "agent_internal_error",
                "The multi-agent run failed unexpectedly.",
            )

    async def _fail_run(
        self,
        session: AsyncSession,
        request: CoordinatorRequest,
        run: AgentRun,
        budget: RunBudget,
        decision: AgentComplexityDecision,
        event_type: str,
        error_code: str,
        safe_message: str,
        *,
        status: AgentRunStatus | None = None,
    ) -> CoordinatorResult:
        target = status or (
            AgentRunStatus.timed_out if event_type == "run_timed_out" else AgentRunStatus.failed
        )
        run.steps_used = budget.steps_used
        run.llm_calls_used = budget.llm_calls_used
        run.tool_calls_used = budget.tool_calls_used
        await self.repository.cancel_queued_tasks(session, run)
        await self.repository.transition_run(
            session,
            run,
            target,
            error_code=error_code,
            safe_error_message=safe_message,
        )
        await self._add_event(
            request,
            session,
            run=run,
            event_type=event_type,
            agent_key="coordinator",
            safe_metadata={"error_code": error_code, **dict(budget.snapshot())},
        )
        return CoordinatorResult(
            execution_mode="multi_agent",
            used_single_agent_fallback=False,
            run=run,
            decision=decision,
            error_code=error_code,
            safe_error_message=safe_message,
        )

    async def resume_after_approval(
        self,
        session: AsyncSession,
        *,
        user: User,
        run: AgentRun,
    ) -> None:
        """Continue only unfinished persisted tasks after an approval gate."""
        request = CoordinatorRequest(
            user=user,
            user_message=run.original_request_summary,
            conversation_id=run.conversation_id,
            memory_enabled=True,
            correlation_id=run.correlation_id,
            enabled_tool_names=frozenset(
                str(name) for task in run.tasks for name in (task.allowed_tools_json or [])
            ),
        )
        budget = RunBudget(
            maximum_steps=run.maximum_steps or self.settings.agent_max_steps,
            max_llm_calls=self.settings.agent_max_llm_calls,
            max_tool_calls=self.settings.agent_max_tool_calls,
            max_context_characters=self.settings.agent_context_max_characters,
            run_timeout_seconds=float(self.settings.agent_run_timeout_seconds),
            steps_used=run.steps_used,
            llm_calls_used=run.llm_calls_used,
            tool_calls_used=run.tool_calls_used,
        )
        envelope = self._build_envelope(request, run.correlation_id)
        budget.observe_context(envelope.character_count())
        task_by_seq = {task.sequence: task for task in run.tasks}
        results_by_seq: dict[int, dict[str, Any]] = {
            task.sequence: {
                "success": task.status == AgentTaskStatus.succeeded,
                "agent_name": task.assigned_agent_key,
                "result_summary": task.result_summary or f"Task {task.status.value}",
            }
            for task in run.tasks
            if task.status
            not in {
                AgentTaskStatus.pending,
                AgentTaskStatus.ready,
                AgentTaskStatus.awaiting_approval,
                AgentTaskStatus.running,
            }
        }
        completed = [
            task
            for task in sorted(run.tasks, key=lambda item: item.sequence)
            if task.status == AgentTaskStatus.succeeded
        ]
        last_agent = completed[-1].assigned_agent_key if completed else "coordinator"

        for task in sorted(run.tasks, key=lambda item: item.sequence):
            if task.status not in {AgentTaskStatus.pending, AgentTaskStatus.ready}:
                continue
            dependencies = [task_by_seq.get(int(seq)) for seq in task.dependencies_json or []]
            if any(dep is None or dep.status != AgentTaskStatus.succeeded for dep in dependencies):
                await self.repository.transition_task(
                    session,
                    task,
                    AgentTaskStatus.skipped,
                    result_summary="Skipped because a dependency did not succeed",
                    error_code="dependency_failed",
                    safe_error_message="A required prior task did not succeed",
                )
                await self._add_event(
                    request,
                    session,
                    run=run,
                    event_type="task_skipped",
                    agent_key=task.assigned_agent_key,
                    task_id=task.id,
                    safe_metadata={"sequence": task.sequence, "reason": "dependency_failed"},
                )
                continue
            if task.status == AgentTaskStatus.pending:
                await self.repository.transition_task(session, task, AgentTaskStatus.ready)
                await self._add_event(
                    request,
                    session,
                    run=run,
                    event_type="task_ready",
                    agent_key=task.assigned_agent_key,
                    task_id=task.id,
                    safe_metadata={"sequence": task.sequence},
                )
            if task.assigned_agent_key != last_agent:
                await self.repository.add_handoff(
                    session,
                    run=run,
                    from_agent_key=last_agent,
                    to_agent_key=task.assigned_agent_key,
                    reason=f"Resume {task.task_type} after approval",
                    task_id=task.id,
                    safe_context_summary="Resumed after user approval",
                )
                await self._add_event(
                    request,
                    session,
                    run=run,
                    event_type="handoff",
                    agent_key=task.assigned_agent_key,
                    task_id=task.id,
                    safe_metadata={"from": last_agent, "to": task.assigned_agent_key},
                )
                last_agent = task.assigned_agent_key
            prior = [results_by_seq[seq] for seq in sorted(results_by_seq)]
            task_envelope = envelope.model_copy(
                update={
                    "prior_task_results": prior,
                    "allowed_tools": list(task.allowed_tools_json or []),
                    "execution_metadata": {
                        **envelope.execution_metadata,
                        "run_id": str(run.id),
                        "task_id": str(task.id),
                        "resumed_after_approval": True,
                    },
                }
            ).enforce_budgets()
            budget.observe_context(task_envelope.character_count())
            result = await self._run_task_with_retries(
                session,
                request=request,
                run=run,
                task=task,
                envelope=task_envelope,
                budget=budget,
            )
            results_by_seq[task.sequence] = result
            if result.get("requires_approval"):
                raise AgentStateTransitionError(
                    "A resumed task requested an unsupported nested approval"
                )

        run.steps_used = budget.steps_used
        run.llm_calls_used = budget.llm_calls_used
        run.tool_calls_used = budget.tool_calls_used
        await self.repository.transition_run(session, run, AgentRunStatus.completed)
        await self._add_event(
            request,
            session,
            run=run,
            event_type="run_completed",
            agent_key="coordinator",
            safe_metadata={"resumed_after_approval": True},
        )

    async def _run_task_with_retries(
        self,
        session: AsyncSession,
        *,
        request: CoordinatorRequest,
        run: AgentRun,
        task: AgentTask,
        envelope: AgentContextEnvelope,
        budget: RunBudget,
    ) -> dict[str, Any]:
        max_retries = min(task.maximum_retries, self.settings.agent_max_retries)
        attempt = 0
        while True:
            budget.consume_step()
            await self.repository.transition_task(session, task, AgentTaskStatus.running)
            await self._add_event(
                request,
                session,
                run=run,
                event_type="task_started",
                agent_key=task.assigned_agent_key,
                task_id=task.id,
                safe_metadata={"sequence": task.sequence, "attempt": attempt},
            )
            try:
                result = await asyncio.wait_for(
                    self._dispatch_task(session, request, task, envelope, budget),
                    timeout=float(self.settings.agent_task_timeout_seconds),
                )
            except TimeoutError:
                await self.repository.transition_task(
                    session,
                    task,
                    AgentTaskStatus.timed_out,
                    error_code="agent_task_timed_out",
                    safe_error_message="Task timed out",
                )
                await self._add_event(
                    request,
                    session,
                    run=run,
                    event_type="task_failed",
                    agent_key=task.assigned_agent_key,
                    task_id=task.id,
                    safe_metadata={"error_code": "agent_task_timed_out"},
                )
                return {
                    "success": False,
                    "agent_name": task.assigned_agent_key,
                    "result_summary": "Task timed out",
                    "error_code": "agent_task_timed_out",
                }
            except AgentLimitExceededError as exc:
                await self.repository.transition_task(
                    session,
                    task,
                    AgentTaskStatus.failed,
                    error_code=exc.code,
                    safe_error_message=str(exc),
                )
                raise

            mapped = self._result_to_dict(result, task)
            if mapped.get("success") or mapped.get("requires_approval"):
                if mapped.get("requires_approval"):
                    # Leave status transition to caller for awaiting_approval.
                    pass
                else:
                    await self.repository.transition_task(
                        session,
                        task,
                        AgentTaskStatus.succeeded,
                        result_summary=str(mapped.get("result_summary") or "")[:2000],
                    )
                await self._add_event(
                    request,
                    session,
                    run=run,
                    event_type="task_completed",
                    agent_key=task.assigned_agent_key,
                    task_id=task.id,
                    safe_metadata={
                        "sequence": task.sequence,
                        "llm_calls_used": mapped.get("llm_calls_used", 0),
                        "tool_calls_used": mapped.get("tool_calls_used", 0),
                        "requires_approval": bool(mapped.get("requires_approval")),
                    },
                )
                return mapped

            retryable = bool(mapped.get("retryable")) or (
                str(mapped.get("error_code") or "") in _RETRYABLE_CODES
            )
            if retryable and attempt < max_retries:
                attempt += 1
                await self.repository.transition_task(
                    session,
                    task,
                    AgentTaskStatus.ready,
                    increment_retry=True,
                    error_code=str(mapped.get("error_code") or "retryable_failure"),
                    safe_error_message=str(mapped.get("safe_error_message") or "Retrying"),
                )
                logger.info(
                    "coordinator_task_retry run_id=%s task_id=%s retry_count=%s error_code=%s",
                    run.id,
                    task.id,
                    attempt,
                    mapped.get("error_code"),
                )
                continue

            await self.repository.transition_task(
                session,
                task,
                AgentTaskStatus.failed,
                error_code=str(mapped.get("error_code") or "task_failed"),
                safe_error_message=str(
                    mapped.get("safe_error_message")
                    or mapped.get("result_summary")
                    or "Task failed"
                )[:500],
            )
            await self._add_event(
                request,
                session,
                run=run,
                event_type="task_failed",
                agent_key=task.assigned_agent_key,
                task_id=task.id,
                safe_metadata={"error_code": mapped.get("error_code"), "retryable": False},
            )
            return mapped

    async def _dispatch_task(
        self,
        session: AsyncSession,
        request: CoordinatorRequest,
        task: AgentTask,
        envelope: AgentContextEnvelope,
        budget: RunBudget,
    ) -> AgentTaskResult:
        agent_key = task.assigned_agent_key
        task_req = AgentTaskRequest(
            task_id=str(task.id),
            sequence=task.sequence,
            agent_name=agent_key,
            task_type=task.task_type,
            objective=task.objective,
            allowed_tools=list(task.allowed_tools_json or []),
            requires_approval=task.requires_approval,
            safe_input_summary=task.safe_input_summary or "",
        )
        from app.agents.base import BaseAgent

        remaining_tools = max(0, budget.max_tool_calls - budget.tool_calls_used)
        kwargs: dict[str, Any] = {
            "session": session,
            "user": request.user,
            "tool_call_budget": remaining_tools,
            "enabled_tool_names": request.enabled_tool_names,
        }
        agent: BaseAgent
        if agent_key == "conversation":
            agent = self.conversation
        elif agent_key == "knowledge":
            agent = self.knowledge
        elif agent_key == "memory":
            agent = self.memory
        elif agent_key == "tool":
            agent = self.tool
        elif agent_key == "planning":
            agent = self.planning
        elif agent_key == "safety":
            agent = self.safety
        else:
            return AgentTaskResult(
                success=False,
                agent_name=agent_key,
                task_type=task.task_type,
                result_summary="Unknown agent",
                error_code="agent_not_found",
                safe_error_message="Unknown agent",
            )

        result = await agent.execute(task=task_req, context=envelope, **kwargs)
        if result.llm_calls_used:
            budget.consume_llm(result.llm_calls_used)
        if result.tool_calls_used:
            budget.consume_tools(result.tool_calls_used)
        # Attach tool execution ids from output when present.
        return result

    async def _synthesize_fallback(
        self,
        session: AsyncSession,
        request: CoordinatorRequest,
        run: AgentRun,
        envelope: AgentContextEnvelope,
        prior: list[dict[str, Any]],
        budget: RunBudget,
    ) -> dict[str, Any]:
        budget.consume_step()
        task_req = AgentTaskRequest(
            sequence=99,
            agent_name="conversation",
            task_type="synthesize",
            objective="Synthesize the final user-facing answer",
        )
        synth_envelope = envelope.model_copy(update={"prior_task_results": prior}).enforce_budgets()
        result = await self.conversation.execute(
            task=task_req, context=synth_envelope, session=session, user=request.user
        )
        if result.llm_calls_used:
            budget.consume_llm(result.llm_calls_used)
        content = ""
        if isinstance(result.output, dict):
            content = str(result.output.get("content") or result.result_summary)
        return {
            "content": content,
            "citations": list((result.output or {}).get("citations") or [])
            if isinstance(result.output, dict)
            else [],
        }

    def _build_envelope(
        self, request: CoordinatorRequest, correlation_id: str
    ) -> AgentContextEnvelope:
        return AgentContextEnvelope(
            user_request=request.user_message[:8000],
            conversation_summary=request.conversation_summary,
            selected_history=list(request.selected_history),
            memory_context=list(request.memory_context),
            document_context=list(request.document_context),
            allowed_tools=sorted(request.enabled_tool_names),
            limits=AgentContextLimits(
                max_characters=self.settings.agent_context_max_characters,
                task_output_max_characters=self.settings.agent_task_output_max_characters,
            ),
            correlation_id=correlation_id,
            conversation_id=request.conversation_id,
            user_id=request.user.id,
            allowed_document_ids=list(request.selected_document_ids),
            execution_metadata={"memory_enabled": request.memory_enabled},
        ).enforce_budgets()

    @staticmethod
    def _task_depth(task: AgentPlanTask, all_tasks: list[AgentPlanTask]) -> int:
        by_seq = {t.sequence: t for t in all_tasks}
        depth = 0
        current_deps = list(task.dependencies)
        seen: set[int] = set()
        while current_deps:
            depth += 1
            nxt: list[int] = []
            for dep in current_deps:
                if dep in seen:
                    continue
                seen.add(dep)
                parent = by_seq.get(dep)
                if parent:
                    nxt.extend(parent.dependencies)
            current_deps = nxt
        return depth

    @staticmethod
    def _result_to_dict(
        result: AgentTaskResult | AgentExecutionResult,
        task: AgentTask,
    ) -> dict[str, Any]:
        if isinstance(result, AgentExecutionResult):
            return {
                "success": result.success and result.status != "failed",
                "agent_name": task.assigned_agent_key,
                "result_summary": result.safe_summary,
                "content": (result.structured_result or {}).get("content"),
                "citations": result.citations,
                "structured_result": result.structured_result,
                "tool_execution_ids": result.tool_execution_ids,
                "llm_calls_used": result.llm_calls_used,
                "tool_calls_used": result.tool_calls_used,
                "retryable": result.retryable,
                "error_code": result.error_code,
                "safe_error_message": result.safe_error_message,
                "requires_approval": result.requires_approval,
                "approval_action_type": result.approval_action_type,
                "approval_summary": result.approval_summary,
            }
        output = result.output if isinstance(result.output, dict) else {}
        retryable = bool(output.get("retryable"))
        return {
            "success": result.success and not (result.error_code and not result.requires_approval),
            "agent_name": result.agent_name,
            "result_summary": result.result_summary,
            "content": output.get("content"),
            "citations": output.get("citations") or [],
            "structured_result": output,
            "output": output,
            "tool_execution_ids": output.get("tool_execution_ids") or [],
            "llm_calls_used": result.llm_calls_used,
            "tool_calls_used": result.tool_calls_used,
            "retryable": retryable,
            "error_code": result.error_code,
            "safe_error_message": result.safe_error_message,
            "requires_approval": result.requires_approval,
            "approval_action_type": result.approval_action_type,
            "approval_summary": result.approval_summary,
        }

    async def _add_event(
        self,
        request: CoordinatorRequest,
        session: AsyncSession,
        *,
        run: AgentRun,
        event_type: str,
        agent_key: str | None = None,
        task_id: UUID | None = None,
        safe_metadata: dict[str, object] | None = None,
    ) -> None:
        await self.repository.add_event(
            session,
            run=run,
            event_type=event_type,
            agent_key=agent_key,
            task_id=task_id,
            safe_metadata=safe_metadata,
        )
        if request.event_callback is not None:
            callback_result = request.event_callback(
                run.id,
                event_type,
                agent_key,
                task_id,
                safe_metadata or {},
            )
            if asyncio.iscoroutine(callback_result):
                await callback_result

    async def _raise_if_cancelled(self, request: CoordinatorRequest) -> None:
        if request.cancel_check is None:
            return
        cancelled = request.cancel_check()
        if asyncio.iscoroutine(cancelled):
            cancelled = await cancelled
        if cancelled:
            raise AgentCancelledError()
