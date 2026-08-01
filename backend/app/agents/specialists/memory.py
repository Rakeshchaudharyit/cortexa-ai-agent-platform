"""Memory Agent — approved memory read and approval-gated writes."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.agents.capabilities import AgentCapability
from app.agents.context import AgentContextEnvelope
from app.agents.schemas import AgentTaskRequest, AgentTaskResult
from app.agents.specialists.common import truncate_output
from app.core.config import Settings
from app.memory.intent import detect_memory_intent
from app.memory.schemas import MemoryIntentKind
from app.models.user import User

logger = logging.getLogger("cortexa.agents.memory")


class MemorySpecialist(BaseAgent):
    name: ClassVar[str] = "memory"
    display_name: ClassVar[str] = "Memory Agent"
    description: ClassVar[str] = (
        "Retrieves approved memories and processes explicit remember, "
        "update, forget, or list requests via MemoryService."
    )
    capabilities: ClassVar[frozenset[AgentCapability]] = frozenset(
        {
            AgentCapability.retrieve_memories,
            AgentCapability.explicit_memory_write,
            AgentCapability.list_memories,
        }
    )
    allowed_tools: ClassVar[frozenset[str]] = frozenset({"memory_list", "memory_search"})
    maximum_steps: ClassVar[int] = 4
    timeout_seconds: ClassVar[int] = 45

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        memory_service: Any | None = None,
        memory_retriever: Any | None = None,
    ) -> None:
        self.settings = settings
        self.memory_service = memory_service
        self.memory_retriever = memory_retriever

    async def execute(
        self,
        *,
        task: AgentTaskRequest,
        context: AgentContextEnvelope,
        **kwargs: Any,
    ) -> AgentTaskResult:
        session: AsyncSession | None = kwargs.get("session")
        user: User | None = kwargs.get("user")
        max_chars = (
            self.settings.agent_task_output_max_characters
            if self.settings is not None
            else context.limits.task_output_max_characters
        )
        memory_enabled = bool((context.execution_metadata or {}).get("memory_enabled", True))
        if not memory_enabled:
            return AgentTaskResult(
                success=True,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary="Memory is disabled for this conversation.",
                output={"memories": [], "memory_disabled": True},
            )

        intent = detect_memory_intent(context.user_request)
        if task.task_type in {"propose_write", "remember", "forget", "update"} or intent.kind in {
            MemoryIntentKind.remember,
            MemoryIntentKind.forget,
            MemoryIntentKind.update,
        }:
            return await self._handle_write(
                task,
                context,
                intent_kind=intent.kind,
                payload=intent.payload or task.objective,
                session=session,
                user=user,
                max_chars=max_chars,
                confirmed=bool(kwargs.get("confirmed")),
            )

        return await self._handle_read(
            task,
            context,
            session=session,
            user=user,
            max_chars=max_chars,
        )

    async def _handle_read(
        self,
        task: AgentTaskRequest,
        context: AgentContextEnvelope,
        *,
        session: AsyncSession | None,
        user: User | None,
        max_chars: int,
    ) -> AgentTaskResult:
        if context.memory_context:
            items = [
                {
                    "title": str(m.get("title") or "Memory"),
                    "summary": truncate_output(
                        str(m.get("content") or m.get("summary") or ""),
                        300,
                    ),
                }
                for m in context.memory_context[: context.limits.max_memory_items]
            ]
            return AgentTaskResult(
                success=True,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary=truncate_output(
                    f"Found {len(items)} approved memor{'y' if len(items) == 1 else 'ies'}.",
                    500,
                ),
                output={"memories": items, "count": len(items)},
            )

        if self.memory_service is None or session is None or user is None:
            return AgentTaskResult(
                success=True,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary="No approved memories were available.",
                output={"memories": [], "count": 0},
            )

        # Ownership enforced by MemoryService — never pass another user's id.
        if context.user_id is not None and str(user.id) != str(context.user_id):
            return AgentTaskResult(
                success=False,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary="Memory access denied.",
                error_code="memory_ownership_denied",
                safe_error_message="Memory access denied.",
            )

        try:
            if self.memory_retriever is not None:
                retrieved = await self.memory_retriever.retrieve(
                    session,
                    user,
                    query=context.user_request,
                    conversation_context=context.conversation_summary,
                    limit=context.limits.max_memory_items,
                )
                items = [
                    {
                        "title": getattr(m, "title", "Memory"),
                        "summary": truncate_output(getattr(m, "content", "") or "", 300),
                    }
                    for m in (retrieved or [])
                ]
            else:
                listed = await self.memory_service.list_for_prompt(
                    session,
                    user,
                    limit=context.limits.max_memory_items,
                )
                items = [
                    {
                        "title": getattr(m, "title", "Memory"),
                        "summary": truncate_output(getattr(m, "content", "") or "", 300),
                    }
                    for m in (listed or [])
                ]
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "memory_read_failed correlation_id=%s error_code=%s",
                context.correlation_id,
                type(exc).__name__,
            )
            return AgentTaskResult(
                success=False,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary="Memory retrieval failed.",
                error_code="memory_retrieval_failed",
                safe_error_message="Memory retrieval failed.",
                output={"retryable": True},
            )

        return AgentTaskResult(
            success=True,
            agent_name=self.name,
            task_type=task.task_type,
            result_summary=truncate_output(
                f"Found {len(items)} approved memor{'y' if len(items) == 1 else 'ies'}.",
                min(500, max_chars),
            ),
            output={"memories": items, "count": len(items)},
        )

    async def _handle_write(
        self,
        task: AgentTaskRequest,
        context: AgentContextEnvelope,
        *,
        intent_kind: MemoryIntentKind,
        payload: str,
        session: AsyncSession | None,
        user: User | None,
        max_chars: int,
        confirmed: bool,
    ) -> AgentTaskResult:
        action = (
            "forget"
            if intent_kind == MemoryIntentKind.forget or task.task_type == "forget"
            else "update"
            if intent_kind == MemoryIntentKind.update or task.task_type == "update"
            else "remember"
        )
        summary = truncate_output(payload or task.objective, 300)

        # Phase 9.2: represent approval-required results internally; do not persist
        # unapproved writes. Confirmed path may call MemoryService when explicitly allowed.
        if not confirmed or task.requires_approval or task.task_type == "propose_write":
            return AgentTaskResult(
                success=True,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary=truncate_output(
                    f"Memory {action} requires approval before it can be applied.",
                    min(500, max_chars),
                ),
                requires_approval=True,
                approval_action_type=f"memory_{action}",
                approval_summary=summary,
                output={
                    "memory_action": {
                        "action": action,
                        "status": "approval_required",
                        "summary": summary,
                        "persisted": False,
                    }
                },
            )

        if self.memory_service is None or session is None or user is None:
            return AgentTaskResult(
                success=False,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary="Memory service unavailable.",
                error_code="memory_service_unavailable",
                safe_error_message="Memory service unavailable.",
            )

        if context.user_id is not None and str(user.id) != str(context.user_id):
            return AgentTaskResult(
                success=False,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary="Memory write denied.",
                error_code="memory_ownership_denied",
                safe_error_message="Memory write denied.",
            )

        # Confirmed writes only — still go through MemoryService policies.
        try:
            if action == "forget":
                await self.memory_service.forget_matching(session, user, query=summary)
            else:
                await self.memory_service.remember_explicit(
                    session,
                    user,
                    summary,
                    conversation_id=context.conversation_id,
                )
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "memory_write_failed correlation_id=%s error_code=%s",
                context.correlation_id,
                type(exc).__name__,
            )
            return AgentTaskResult(
                success=False,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary="Memory write failed.",
                error_code="memory_write_failed",
                safe_error_message="Memory write failed.",
            )

        return AgentTaskResult(
            success=True,
            agent_name=self.name,
            task_type=task.task_type,
            result_summary=truncate_output(f"Memory {action} applied.", 500),
            output={
                "memory_action": {
                    "action": action,
                    "status": "applied",
                    "summary": summary,
                    "persisted": True,
                }
            },
        )
