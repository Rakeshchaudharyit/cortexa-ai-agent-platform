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
from app.agents.failures import FailureClassifier
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
from app.agents.telemetry import (
    PhaseTimer,
    apply_budget_snapshot,
    calculate_execution_duration_ms,
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
    force_multi_agent: bool = False
    execution_profile: str = "fast"


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
        self.failure_classifier = FailureClassifier()
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


    @staticmethod
    def _profile_limits(profile: str) -> tuple[int, int, int, bool]:
        """Return run, specialist, synthesis limits and timeout-retry policy."""
        normalized = profile if profile in {"fast", "balanced", "deep"} else "fast"
        if normalized == "balanced":
            return (150, 60, 30, True)
        if normalized == "deep":
            return (240, 90, 45, True)
        return (90, 35, 20, False)

    async def execute(
        self,
        session: AsyncSession,
        request: CoordinatorRequest,
    ) -> CoordinatorResult:
        correlation_id = request.correlation_id or str(uuid.uuid4())
        if request.force_multi_agent:
            decision = AgentComplexityDecision(
                execution_mode="multi_agent",
                confidence=1.0,
                reason_codes=["user_forced_multi_agent", f"profile_{request.execution_profile}"],
                required_capabilities=["planning", "knowledge", "response"],
                suggested_agents=["planning", "knowledge", "conversation"],
                requires_planning=True,
                safe_summary="User explicitly requested coordinated specialist execution",
            )
        else:
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
        run_id = run.id
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
            safe_metadata={
                "execution_mode": "multi_agent",
                "execution_profile": request.execution_profile,
                "forced_by_user": request.force_multi_agent,
            },
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
        # Persist a single durable start checkpoint before provider work. Do not
        # commit from event callbacks while task/provider awaits are active.
        await session.commit()
        await session.refresh(run)
        logger.info(
            "coordinator_start_checkpoint run_id=%s correlation_id=%s",
            run.id,
            correlation_id,
        )

        run_limit, _, _, _ = self._profile_limits(request.execution_profile)
        budget = RunBudget(
            maximum_steps=run.maximum_steps or self.settings.agent_max_steps,
            max_llm_calls=self.settings.agent_max_llm_calls,
            max_tool_calls=self.settings.agent_max_tool_calls,
            max_context_characters=self.settings.agent_context_max_characters,
            run_timeout_seconds=float(min(self.settings.agent_run_timeout_seconds, run_limit)),
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

            planning_timer = PhaseTimer()
            plan = await self.planning.create_plan(
                user_request=request.user_message,
                decision=decision,
                enabled_tool_names=request.enabled_tool_names,
                selected_document_ids=[str(d) for d in request.selected_document_ids],
                memory_enabled=request.memory_enabled,
                execution_profile=request.execution_profile,
            )
            run.planning_duration_ms = planning_timer.elapsed_ms()
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
                    "planning_strategy": plan.planning_strategy,
                    "planning_duration_ms": run.planning_duration_ms,
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

            # Persist the validated task graph before any external provider call.
            # This creates a clean transaction boundary for timeout recovery and
            # browser reconnects without committing from SSE callbacks.
            await session.commit()
            await session.refresh(run)
            for persisted_task in tasks:
                await session.refresh(persisted_task)
            logger.info(
                "coordinator_plan_checkpoint run_id=%s correlation_id=%s task_count=%s",
                run.id,
                correlation_id,
                len(tasks),
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
                # Checkpoint only between tasks, never while a provider await is
                # active. This preserves completed specialist work and keeps ORM
                # state valid for the next task.
                await session.commit()
                await session.refresh(run)
                await session.refresh(task)
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
                synthesis_timer = PhaseTimer()
                synth = await self._synthesize_fallback(
                    session, request, run, envelope, ordered_results, budget
                )
                final_content = synth.get("content") or ""
                citations.extend(synth.get("citations") or [])
                run.synthesis_duration_ms = synthesis_timer.elapsed_ms()

            apply_budget_snapshot(run, budget)
            run.execution_duration_ms = calculate_execution_duration_ms(run)
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
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "coordinator_unexpected_failure correlation_id=%s exception_type=%s "
                "exception_message=%s",
                correlation_id,
                type(exc).__name__,
                str(exc),
            )
            # A failed provider/task await may leave the transaction unusable.
            # Roll back explicitly and re-load the durable run before recording
            # the terminal failure, avoiding implicit ORM I/O (MissingGreenlet).
            await session.rollback()
            reloaded = await self.repository.get_by_id(session, run_id)
            if reloaded is not None:
                run = reloaded
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
        failure = self.failure_classifier.classify(
            error_code=error_code,
            retryable_hint=False if target == AgentRunStatus.cancelled else None,
            safe_message=safe_message,
        )
        apply_budget_snapshot(run, budget)
        run.execution_duration_ms = calculate_execution_duration_ms(run)
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
            safe_metadata={**failure.safe_metadata(), **dict(budget.snapshot())},
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
            run_timeout_seconds=float(
                min(self.settings.agent_run_timeout_seconds, 90)
                if self.settings.agent_interactive_fast_mode
                else self.settings.agent_run_timeout_seconds
            ),
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

        apply_budget_snapshot(run, budget)
        run.execution_duration_ms = calculate_execution_duration_ms(run)
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
        _, specialist_limit, synthesis_limit, retry_timeouts = self._profile_limits(
            request.execution_profile
        )
        # Snapshot scalar fields before any provider await. ORM attributes must
        # not be the source of implicit I/O after a timeout/cancellation boundary.
        task_id = task.id
        agent_key = task.assigned_agent_key
        task_sequence = task.sequence
        task_type = task.task_type
        task_objective = task.objective
        task_dependencies = list(task.dependencies_json or [])
        task_allowed_tools = list(task.allowed_tools_json or [])
        task_requires_approval = task.requires_approval
        task_maximum_retries = task.maximum_retries
        max_retries = min(task_maximum_retries, self.settings.agent_max_retries)
        attempt = 0
        while True:
            budget.consume_step()
            await self.repository.transition_task(session, task, AgentTaskStatus.running)
            await self._add_event(
                request,
                session,
                run=run,
                event_type="task_started",
                agent_key=agent_key,
                task_id=task_id,
                safe_metadata={"sequence": task_sequence, "attempt": attempt},
            )
            try:
                if agent_key == "conversation":
                    requested_timeout = min(
                        self.settings.agent_synthesis_timeout_seconds, synthesis_limit
                    )
                else:
                    requested_timeout = min(
                        self.settings.agent_task_timeout_seconds, specialist_limit
                    )
                effective_timeout = budget.bounded_timeout(float(requested_timeout))
                result = await asyncio.wait_for(
                    self._dispatch_task(session, request, task, envelope, budget),
                    timeout=effective_timeout,
                )
                await session.refresh(task)
            except TimeoutError as exc:
                await session.refresh(task)
                # Final synthesis must degrade gracefully on slow local models.
                # Earlier specialist results are already persisted and safe to summarize,
                # so a Conversation Agent timeout should not turn the whole run into an
                # opaque internal failure.
                if agent_key == "conversation":
                    task_req = AgentTaskRequest(
                        sequence=task_sequence,
                        agent_name=agent_key,
                        task_type=task_type,
                        objective=task_objective,
                        dependencies=task_dependencies,
                        allowed_tools=task_allowed_tools,
                        requires_approval=task_requires_approval,
                        maximum_retries=task_maximum_retries,
                    )
                    fallback_result = self.conversation.build_deterministic_fallback(
                        task=task_req,
                        context=envelope,
                    )
                    mapped = self._result_to_dict(fallback_result, task)
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
                        agent_key=agent_key,
                        task_id=task_id,
                        safe_metadata={
                            "sequence": task_sequence,
                            "degraded_synthesis": True,
                            "reason": "provider_timeout",
                            "llm_calls_used": 0,
                            "tool_calls_used": 0,
                            "requires_approval": False,
                        },
                    )
                    return mapped

                decision = self.failure_classifier.classify(
                    error=exc,
                    error_code="agent_task_timed_out",
                    safe_message="Task timed out",
                )
                if (
                    decision.retryable
                    and attempt < max_retries
                    and retry_timeouts
                ):
                    attempt += 1
                    await self.repository.transition_task(
                        session,
                        task,
                        AgentTaskStatus.ready,
                        increment_retry=True,
                        error_code=decision.error_code,
                        safe_error_message=decision.safe_message,
                    )
                    await self._add_event(
                        request,
                        session,
                        run=run,
                        event_type="task_retrying",
                        agent_key=agent_key,
                        task_id=task_id,
                        safe_metadata={
                            **decision.safe_metadata(),
                            "attempt": attempt,
                            "maximum_retries": max_retries,
                        },
                    )
                    continue
                await self.repository.transition_task(
                    session,
                    task,
                    AgentTaskStatus.timed_out,
                    error_code=decision.error_code,
                    safe_error_message=decision.safe_message,
                )
                await self._add_event(
                    request,
                    session,
                    run=run,
                    event_type="task_failed",
                    agent_key=agent_key,
                    task_id=task_id,
                    safe_metadata=decision.safe_metadata(),
                )
                return {
                    "success": False,
                    "agent_name": agent_key,
                    "result_summary": decision.safe_message,
                    "error_code": decision.error_code,
                    "failure_category": decision.category.value,
                    "retryable": decision.retryable,
                }
            except AgentLimitExceededError as exc:
                await session.refresh(task)
                await self.repository.transition_task(
                    session,
                    task,
                    AgentTaskStatus.failed,
                    error_code=exc.code,
                    safe_error_message=str(exc),
                )
                raise
            except Exception as exc:  # noqa: BLE001
                await session.refresh(task)
                # Local providers can fail with provider-specific timeout or connection
                # exceptions that are not asyncio.TimeoutError. Final synthesis still
                # has enough persisted specialist context to return a safe degraded
                # answer, so do not fail the entire run for that case.
                if agent_key == "conversation":
                    logger.info(
                        "conversation_synthesis_degraded run_id=%s task_id=%s "
                        "error_code=%s",
                        run.id,
                        task_id,
                        type(exc).__name__,
                    )
                    task_req = AgentTaskRequest(
                        sequence=task_sequence,
                        agent_name=agent_key,
                        task_type=task_type,
                        objective=task_objective,
                        dependencies=task_dependencies,
                        allowed_tools=task_allowed_tools,
                        requires_approval=task_requires_approval,
                        maximum_retries=task_maximum_retries,
                    )
                    fallback_result = self.conversation.build_deterministic_fallback(
                        task=task_req,
                        context=envelope,
                    )
                    mapped = self._result_to_dict(fallback_result, task)
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
                        agent_key=agent_key,
                        task_id=task_id,
                        safe_metadata={
                            "sequence": task_sequence,
                            "degraded_synthesis": True,
                            "reason": "provider_error",
                            "error_code": type(exc).__name__,
                            "llm_calls_used": 0,
                            "tool_calls_used": 0,
                            "requires_approval": False,
                        },
                    )
                    return mapped

                decision = self.failure_classifier.classify(error=exc)
                if decision.retryable and attempt < max_retries:
                    attempt += 1
                    await self.repository.transition_task(
                        session,
                        task,
                        AgentTaskStatus.ready,
                        increment_retry=True,
                        error_code=decision.error_code,
                        safe_error_message=decision.safe_message,
                    )
                    await self._add_event(
                        request,
                        session,
                        run=run,
                        event_type="task_retrying",
                        agent_key=agent_key,
                        task_id=task_id,
                        safe_metadata={
                            **decision.safe_metadata(),
                            "attempt": attempt,
                            "maximum_retries": max_retries,
                        },
                    )
                    continue
                await self.repository.transition_task(
                    session,
                    task,
                    AgentTaskStatus.failed,
                    error_code=decision.error_code,
                    safe_error_message=decision.safe_message,
                )
                await self._add_event(
                    request,
                    session,
                    run=run,
                    event_type="task_failed",
                    agent_key=agent_key,
                    task_id=task_id,
                    safe_metadata=decision.safe_metadata(),
                )
                return {
                    "success": False,
                    "agent_name": agent_key,
                    "result_summary": decision.safe_message,
                    "error_code": decision.error_code,
                    "safe_error_message": decision.safe_message,
                    "failure_category": decision.category.value,
                    "retryable": decision.retryable,
                }

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
                    agent_key=agent_key,
                    task_id=task_id,
                    safe_metadata={
                        "sequence": task_sequence,
                        "llm_calls_used": mapped.get("llm_calls_used", 0),
                        "tool_calls_used": mapped.get("tool_calls_used", 0),
                        "requires_approval": bool(mapped.get("requires_approval")),
                    },
                )
                return mapped

            decision = self.failure_classifier.classify(
                error_code=str(mapped.get("error_code") or "task_failed"),
                retryable_hint=(
                    bool(mapped.get("retryable")) if "retryable" in mapped else None
                ),
                safe_message=str(
                    mapped.get("safe_error_message")
                    or mapped.get("result_summary")
                    or "Task failed"
                ),
            )
            mapped["failure_category"] = decision.category.value
            mapped["retryable"] = decision.retryable
            if decision.retryable and attempt < max_retries:
                attempt += 1
                await self.repository.transition_task(
                    session,
                    task,
                    AgentTaskStatus.ready,
                    increment_retry=True,
                    error_code=decision.error_code,
                    safe_error_message=decision.safe_message,
                )
                await self._add_event(
                    request,
                    session,
                    run=run,
                    event_type="task_retrying",
                    agent_key=agent_key,
                    task_id=task_id,
                    safe_metadata={
                        **decision.safe_metadata(),
                        "attempt": attempt,
                        "maximum_retries": max_retries,
                    },
                )
                logger.info(
                    "coordinator_task_retry run_id=%s task_id=%s retry_count=%s "
                    "error_code=%s failure_category=%s",
                    run.id,
                    task_id,
                    attempt,
                    decision.error_code,
                    decision.category.value,
                )
                continue

            await self.repository.transition_task(
                session,
                task,
                AgentTaskStatus.failed,
                error_code=decision.error_code,
                safe_error_message=decision.safe_message,
            )
            await self._add_event(
                request,
                session,
                run=run,
                event_type="task_failed",
                agent_key=agent_key,
                task_id=task_id,
                safe_metadata=decision.safe_metadata(),
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
        try:
            result = await asyncio.wait_for(
                self.conversation.execute(
                    task=task_req, context=synth_envelope, session=session, user=request.user
                ),
                timeout=budget.bounded_timeout(
                    float(
                        min(
                            self.settings.agent_synthesis_timeout_seconds,
                            self._profile_limits(request.execution_profile)[2],
                        )
                    )
                ),
            )
        except Exception:  # noqa: BLE001
            result = self.conversation.build_deterministic_fallback(
                task=task_req,
                context=synth_envelope,
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
