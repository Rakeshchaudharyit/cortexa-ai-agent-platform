"""Tool Agent — executes allow-listed tools via ToolExecutor."""

from __future__ import annotations

import logging
import re
from typing import Any, ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.agents.capabilities import AgentCapability
from app.agents.context import AgentContextEnvelope
from app.agents.schemas import AgentTaskRequest, AgentTaskResult
from app.agents.specialists.common import truncate_output
from app.core.config import Settings
from app.models.enums import UserRole
from app.models.user import User

logger = logging.getLogger("cortexa.agents.tool")

_EXPRESSION = re.compile(
    r"(?P<expr>\d[\d,\.\s]*[+\-*/×÷^%]\s*\d[\d,\.\s*%]*(?:\s*[+\-*/×÷^%]\s*\d[\d,\.\s*%]*)*)"
)
_TZ = re.compile(r"\b(?P<tz>[A-Za-z]+/[A-Za-z_]+(?:/[A-Za-z_]+)?)\b")


class ToolSpecialist(BaseAgent):
    name: ClassVar[str] = "tool"
    display_name: ClassVar[str] = "Tool Agent"
    description: ClassVar[str] = (
        "Executes registered and enabled tools through ToolExecutor with "
        "argument validation and execution audits."
    )
    capabilities: ClassVar[frozenset[AgentCapability]] = frozenset(
        {
            AgentCapability.execute_tools,
            AgentCapability.validate_arguments,
        }
    )
    allowed_tools: ClassVar[frozenset[str]] = frozenset(
        {
            "calculator",
            "current_datetime",
            "conversation_summary",
        }
    )
    maximum_steps: ClassVar[int] = 4
    timeout_seconds: ClassVar[int] = 45

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        tool_executor: Any | None = None,
        tool_registry: Any | None = None,
    ) -> None:
        self.settings = settings
        self.tool_executor = tool_executor
        self.tool_registry = tool_registry

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
        raw_budget = kwargs.get("tool_call_budget")
        if raw_budget is None:
            budget = int(self.settings.agent_max_tool_calls if self.settings else 8)
        else:
            budget = int(raw_budget)
        if budget <= 0:
            return AgentTaskResult(
                success=False,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary="Tool-call budget exhausted.",
                error_code="tool_budget_exceeded",
                safe_error_message="Tool-call budget exhausted.",
            )

        allowlist = set(task.allowed_tools or context.allowed_tools or []) & set(self.allowed_tools)
        if not allowlist:
            # Infer from objective when plan omitted tools but agent allow-list applies.
            text = f"{task.objective} {context.user_request}"
            if _EXPRESSION.search(text) or re.search(r"(?i)\bcalculat|percent|%\b", text):
                allowlist.add("calculator")
            if _TZ.search(text) or re.search(r"(?i)\b(time|date|timezone|clock)\b", text):
                allowlist.add("current_datetime")
            allowlist &= set(self.allowed_tools)

        if not allowlist:
            return AgentTaskResult(
                success=False,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary="No allowed tools were available for this task.",
                error_code="tool_not_allowed",
                safe_error_message="No allowed tools were available for this task.",
            )

        if self.tool_executor is None or session is None or user is None:
            return AgentTaskResult(
                success=False,
                agent_name=self.name,
                task_type=task.task_type,
                result_summary="Tool executor unavailable.",
                error_code="tool_executor_unavailable",
                safe_error_message="Tool executor unavailable.",
            )

        # Prefer calculator / datetime for structured results; avoid knowledge/memory tools
        # when specialist agents already cover those capabilities.
        preferred_order = ("calculator", "current_datetime", "conversation_summary")
        selected = [name for name in preferred_order if name in allowlist][:budget]
        tool_execution_ids: list[str] = []
        results: list[dict[str, Any]] = []
        calls_used = 0

        for tool_name in selected:
            ok, payload = await self._execute_one(
                session=session,
                user=user,
                context=context,
                tool_name=tool_name,
                task=task,
            )
            calls_used += 1
            if not ok:
                return AgentTaskResult(
                    success=False,
                    agent_name=self.name,
                    task_type=task.task_type,
                    result_summary=str(payload.get("error") or "Tool execution failed"),
                    error_code=str(payload.get("error_code") or "tool_execution_failed"),
                    safe_error_message=str(payload.get("error") or "Tool execution failed"),
                    tool_calls_used=calls_used,
                    output={"tool_results": results, "tool_execution_ids": tool_execution_ids},
                )
            if payload.get("execution_id"):
                tool_execution_ids.append(str(payload["execution_id"]))
            results.append(
                {
                    "tool_name": tool_name,
                    "result": payload.get("result"),
                    "success": True,
                }
            )

        summary = "; ".join(
            f"{item['tool_name']}: {truncate_output(str(item.get('result')), 200)}"
            for item in results
        )
        return AgentTaskResult(
            success=True,
            agent_name=self.name,
            task_type=task.task_type,
            result_summary=truncate_output(summary or "Tools executed.", min(2000, max_chars)),
            tool_calls_used=calls_used,
            output={
                "tool_result": results[0]["result"] if len(results) == 1 else results,
                "tool_results": results,
                "tool_execution_ids": tool_execution_ids,
            },
        )

    async def _execute_one(
        self,
        *,
        session: AsyncSession,
        user: User,
        context: AgentContextEnvelope,
        tool_name: str,
        task: AgentTaskRequest,
    ) -> tuple[bool, dict[str, Any]]:
        assert self.tool_executor is not None

        # Validate against registry + enabled configuration.
        if self.tool_registry is not None:
            try:
                tool = self.tool_registry.get(tool_name)
            except Exception:  # noqa: BLE001
                return False, {
                    "error_code": "tool_unregistered",
                    "error": "Tool is not registered.",
                }
            role = user.role if isinstance(user.role, UserRole) else UserRole.user
            enabled = {t.name for t in self.tool_registry.list_enabled(role=role)}
            if tool_name not in enabled or not getattr(tool, "enabled", True):
                return False, {
                    "error_code": "tool_disabled",
                    "error": "Tool is disabled.",
                }

        arguments = self._build_arguments(tool_name, context, task)
        try:
            execution, result = await self.tool_executor.execute(
                session=session,
                tool_name=tool_name,
                arguments=arguments,
                user_id=user.id,
                user_role=user.role,
                conversation_id=context.conversation_id,
                correlation_id=context.correlation_id,
                allowed_document_ids=list(context.allowed_document_ids) or None,
                persist=True,
            )
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", None) or type(exc).__name__
            non_retryable = {
                "tool_invalid_arguments",
                "tool_permission_denied",
                "tool_not_found",
                "tool_disabled",
                "ToolInvalidArgumentsError",
                "ToolPermissionDeniedError",
                "ToolNotFoundError",
                "ToolDisabledError",
            }
            return False, {
                "error_code": str(code),
                "error": "Tool execution failed.",
                "retryable": str(code) not in non_retryable,
            }

        success = bool(getattr(result, "success", False))
        if not success:
            return False, {
                "error_code": getattr(result, "error_code", None) or "tool_execution_failed",
                "error": getattr(result, "error_message", None)
                or getattr(result, "error", None)
                or "Tool execution failed.",
            }
        return True, {
            "execution_id": str(execution.id) if execution is not None else None,
            "result": getattr(result, "data", None) or {},
        }

    def _build_arguments(
        self,
        tool_name: str,
        context: AgentContextEnvelope,
        task: AgentTaskRequest,
    ) -> dict[str, Any]:
        text = f"{task.objective}\n{context.user_request}"
        if tool_name == "calculator":
            match = _EXPRESSION.search(text.replace("×", "*").replace("÷", "/"))
            expression = match.group("expr") if match else ""
            # Normalize unicode operators and commas.
            expression = expression.replace("×", "*").replace("÷", "/").replace(",", "").strip()
            if not expression:
                # Fallback: extract "15 percent of X" style when present.
                pct = re.search(
                    r"(?i)(\d+(?:\.\d+)?)\s*(?:percent|%)\s*(?:of\s+)?(\d+(?:\.\d+)?)",
                    text,
                )
                if pct:
                    expression = f"({pct.group(1)}/100)*{pct.group(2)}"
            return {"expression": expression or "0"}
        if tool_name == "current_datetime":
            tz_match = _TZ.search(text)
            return {"timezone": tz_match.group("tz") if tz_match else "UTC"}
        if tool_name == "conversation_summary":
            return {"focus": truncate_output(task.objective, 200)}
        return {}
