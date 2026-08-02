"""Feature-gated multi-agent orchestration service."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.classifier import ComplexityClassifier
from app.agents.coordinator import CoordinatorEngine, CoordinatorRequest, CoordinatorResult
from app.agents.registry import AgentRegistry
from app.agents.repository import AgentRunRepository
from app.agents.schemas import AgentComplexityDecision, ClassifierInput
from app.core.config import Settings
from app.models.user import User

logger = logging.getLogger("cortexa.agents.multi_agent")


class MultiAgentService:
    """Internal multi-agent entrypoint. Public APIs arrive in Phase 9.3."""

    def __init__(
        self,
        *,
        settings: Settings,
        registry: AgentRegistry,
        repository: AgentRunRepository,
        coordinator: CoordinatorEngine | None = None,
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
        self.classifier = classifier or ComplexityClassifier(settings, llm_service=llm_service)
        self.coordinator = coordinator or CoordinatorEngine(
            settings=settings,
            registry=registry,
            repository=repository,
            classifier=self.classifier,
            llm_service=llm_service,
            retrieval_service=retrieval_service,
            memory_service=memory_service,
            memory_retriever=memory_retriever,
            tool_executor=tool_executor,
            tool_registry=tool_registry,
        )
        self._cancel_events: dict[UUID, asyncio.Event] = {}
        self._active_tasks: dict[UUID, asyncio.Task[Any]] = {}

    def request_cancel(self, run_id: UUID) -> None:
        """Signal an active in-process coordinator/provider cancellation hook."""
        event = self._cancel_events.get(run_id)
        if event is not None:
            event.set()
        task = self._active_tasks.get(run_id)
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.multi_agent_enabled)

    async def classify(
        self,
        *,
        user_message: str,
        conversation_mode: str = "general",
        selected_document_ids: list[UUID] | None = None,
        memory_enabled: bool = False,
        explicit_memory_intent: bool = False,
        selected_tool_intent: list[str] | None = None,
        conversation_context_summary: str | None = None,
    ) -> AgentComplexityDecision:
        return await self.classifier.classify(
            ClassifierInput(
                user_message=user_message,
                conversation_mode=conversation_mode,
                selected_document_ids=[str(d) for d in (selected_document_ids or [])],
                memory_enabled=memory_enabled,
                explicit_memory_intent=explicit_memory_intent,
                selected_tool_intent=list(selected_tool_intent or []),
                conversation_context_summary=conversation_context_summary,
                enabled_feature_flags={"multi_agent_enabled": self.enabled},
            )
        )

    def should_use_multi_agent(self, decision: AgentComplexityDecision) -> bool:
        return (
            self.enabled and decision.execution_mode == "multi_agent" and decision.requires_planning
        )

    async def execute(
        self,
        session: AsyncSession,
        *,
        user: User,
        user_message: str,
        conversation_id: UUID | None = None,
        conversation_mode: str = "general",
        selected_document_ids: list[UUID] | None = None,
        memory_enabled: bool = False,
        explicit_memory_intent: bool = False,
        selected_tool_intent: list[str] | None = None,
        conversation_summary: str | None = None,
        selected_history: list[dict[str, str]] | None = None,
        memory_context: list[dict[str, Any]] | None = None,
        document_context: list[dict[str, Any]] | None = None,
        correlation_id: str = "",
        enabled_tool_names: frozenset[str] | None = None,
        cancel_check: Any | None = None,
        event_callback: Any | None = None,
    ) -> CoordinatorResult:
        if correlation_id:
            existing = await self.repository.get_by_correlation(
                session,
                user=user,
                conversation_id=conversation_id,
                correlation_id=correlation_id,
            )
            if existing is not None:
                return CoordinatorResult(
                    execution_mode=existing.execution_mode.value,
                    used_single_agent_fallback=False,
                    run=existing,
                    approval_required=existing.status.value == "awaiting_approval",
                    error_code=existing.error_code,
                    safe_error_message=existing.safe_error_message,
                )
        cancel_event = asyncio.Event()
        active_run_id: UUID | None = None

        def register_run(run_id: UUID) -> None:
            nonlocal active_run_id
            active_run_id = run_id
            self._cancel_events[run_id] = cancel_event
            current = asyncio.current_task()
            if current is not None:
                self._active_tasks[run_id] = current

        async def combined_cancel_check() -> bool:
            if cancel_event.is_set():
                return True
            if cancel_check is None:
                return False
            value = cancel_check()
            if asyncio.iscoroutine(value):
                value = await value
            return bool(value)

        request = CoordinatorRequest(
            user=user,
            user_message=user_message,
            conversation_id=conversation_id,
            conversation_mode=conversation_mode,
            selected_document_ids=list(selected_document_ids or []),
            memory_enabled=memory_enabled,
            explicit_memory_intent=explicit_memory_intent,
            selected_tool_intent=list(selected_tool_intent or []),
            conversation_summary=conversation_summary,
            selected_history=list(selected_history or []),
            memory_context=list(memory_context or []),
            document_context=list(document_context or []),
            correlation_id=correlation_id,
            enabled_tool_names=enabled_tool_names or frozenset(),
            cancel_check=combined_cancel_check,
            on_run_created=register_run,
            event_callback=event_callback,
        )
        try:
            result = await self.coordinator.execute(session, request)
        finally:
            if active_run_id is not None:
                self._cancel_events.pop(active_run_id, None)
                self._active_tasks.pop(active_run_id, None)
        logger.info(
            "multi_agent_execute_finished correlation_id=%s execution_mode=%s "
            "fallback=%s error_code=%s",
            correlation_id or "-",
            result.execution_mode,
            result.used_single_agent_fallback,
            result.error_code or "-",
        )
        return result
