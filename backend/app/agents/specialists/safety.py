"""Safety Agent — deterministic policy validation with optional model assist."""

from __future__ import annotations

import logging
import re
from typing import Any, ClassVar

from app.agents.base import BaseAgent
from app.agents.capabilities import SYSTEM_AGENT_KEYS, AgentCapability
from app.agents.context import AgentContextEnvelope
from app.agents.registry import AgentRegistry
from app.agents.schemas import (
    AgentPlan,
    AgentTaskRequest,
    AgentTaskResult,
    SafetyDecision,
)
from app.agents.specialists.common import detect_prompt_injection, load_json_object
from app.core.config import Settings
from app.llm.schemas import ChatMessage, GenerateRequest, MessageRole

logger = logging.getLogger("cortexa.agents.safety")

_SHELL = re.compile(
    r"(?i)\b(rm\s+-rf|sudo\s+|bash\s+-c|/bin/(?:sh|bash)|powershell|"
    r"cmd\.exe|os\.system|subprocess\.|shell\s+command)\b"
)
_SQL = re.compile(
    r"(?i)\b(drop\s+table|delete\s+from|truncate\s+table|union\s+select|"
    r"insert\s+into|alter\s+table|information_schema|;--)\b"
)
_SYSTEM_PROMPT = re.compile(
    r"(?i)(\b(reveal|show|print|dump)\b.{0,40}\b(system\s+prompt|hidden\s+instructions?|"
    r"developer\s+message)\b|"
    r"\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions?\b)"
)
_CROSS_USER = re.compile(
    r"(?i)\b(another\s+user(?:'s)?|other\s+users?(?:'\s*)?|"
    r"all\s+users?(?:'\s*)?\s+(?:documents?|memor(?:y|ies)|data)|"
    r"everyone(?:'s)?\s+(?:documents?|memor(?:y|ies)))\b"
)
_EXTERNAL = re.compile(
    r"(?i)\b(send\s+(?:an?\s+)?email|call\s+(?:an?\s+)?external\s+api|"
    r"webhook|exfiltrat|post\s+to\s+https?://)\b"
)
_CODE_EXEC = re.compile(
    r"(?i)\b(eval\s*\(|exec\s*\(|__import__|compile\s*\(|"
    r"write\s+(?:to\s+)?(?:disk|/etc|/var)|read\s+/etc/passwd)\b"
)


class SafetySpecialist(BaseAgent):
    name: ClassVar[str] = "safety"
    display_name: ClassVar[str] = "Safety Agent"
    description: ClassVar[str] = (
        "Validates plans, rejects unregistered agents and unauthorized tools, "
        "detects prompt-injection and policy bypass attempts, and requires "
        "approval for sensitive writes."
    )
    capabilities: ClassVar[frozenset[AgentCapability]] = frozenset(
        {
            AgentCapability.validate_plan,
            AgentCapability.detect_injection,
            AgentCapability.require_approval,
            AgentCapability.reject_unauthorized,
        }
    )
    allowed_tools: ClassVar[frozenset[str]] = frozenset()
    maximum_steps: ClassVar[int] = 2
    timeout_seconds: ClassVar[int] = 30
    required_for_multi_agent: ClassVar[bool] = True

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
        plan = kwargs.get("plan")
        enabled_tools = frozenset(kwargs.get("enabled_tool_names") or context.allowed_tools or [])
        if isinstance(plan, AgentPlan):
            decision = await self.review_plan(
                plan,
                user_request=context.user_request,
                enabled_tool_names=enabled_tools,
            )
        else:
            decision = self.review_request(context.user_request)
        return AgentTaskResult(
            success=not decision.blocked,
            agent_name=self.name,
            task_type=task.task_type,
            result_summary=decision.safe_message or ("Allowed" if decision.allowed else "Blocked"),
            output={"safety": decision.model_dump()},
            requires_approval=decision.requires_approval,
            error_code="agent_safety_rejected" if decision.blocked else None,
            safe_error_message=decision.safe_message if decision.blocked else None,
        )

    def review_request(self, user_request: str) -> SafetyDecision:
        text = user_request or ""
        codes: list[str] = []
        if _SHELL.search(text) or _CODE_EXEC.search(text):
            codes.append("shell_or_code_request")
        if _SQL.search(text):
            codes.append("arbitrary_sql_request")
        if _SYSTEM_PROMPT.search(text):
            codes.append("system_prompt_extraction")
        if _CROSS_USER.search(text):
            codes.append("cross_user_access")
        if _EXTERNAL.search(text):
            codes.append("unsupported_external_integration")
        injection = detect_prompt_injection(text)
        # User-authored injection attempts targeting the system are blocked;
        # document injection is handled as untrusted data elsewhere.
        if injection and _SYSTEM_PROMPT.search(text):
            codes.append("prompt_injection_instruction")

        if codes:
            return SafetyDecision(
                allowed=False,
                blocked=True,
                reason_codes=codes,
                safe_message="This request cannot be completed due to safety policy.",
            )
        return SafetyDecision(
            allowed=True,
            blocked=False,
            reason_codes=["request_allowed"],
            safe_message="Request passed safety checks",
        )

    async def review_plan(
        self,
        plan: AgentPlan,
        *,
        user_request: str,
        enabled_tool_names: frozenset[str] | None = None,
    ) -> SafetyDecision:
        """Deterministic plan + request review. Model assist only when ambiguous."""
        request_decision = self.review_request(user_request)
        if request_decision.blocked:
            return request_decision

        codes: list[str] = list(request_decision.reason_codes)
        requires_approval = bool(plan.requires_approval)

        if self.registry is not None:
            for task in plan.tasks:
                if task.agent_name not in self.registry.names():
                    return SafetyDecision(
                        allowed=False,
                        blocked=True,
                        reason_codes=["unknown_agent"],
                        safe_message="Plan references an unknown agent.",
                    )
                if task.agent_name not in SYSTEM_AGENT_KEYS:
                    return SafetyDecision(
                        allowed=False,
                        blocked=True,
                        reason_codes=["unregistered_agent"],
                        safe_message="Plan references an unregistered agent.",
                    )
                try:
                    self.registry.require_enabled(task.agent_name)
                except Exception:  # noqa: BLE001
                    return SafetyDecision(
                        allowed=False,
                        blocked=True,
                        reason_codes=["disabled_agent"],
                        safe_message="Plan references a disabled agent.",
                    )
                agent = self.registry.get(task.agent_name)
                allowed = self.registry.effective_allowed_tools(agent)
                for tool in task.allowed_tools:
                    if tool not in allowed:
                        return SafetyDecision(
                            allowed=False,
                            blocked=True,
                            reason_codes=["unauthorized_tool"],
                            safe_message="Plan includes a tool this agent may not use.",
                        )
                    if enabled_tool_names is not None and tool not in enabled_tool_names:
                        return SafetyDecision(
                            allowed=False,
                            blocked=True,
                            reason_codes=["disabled_tool"],
                            safe_message="Plan includes a disabled tool.",
                        )
                if task.requires_approval:
                    requires_approval = True
                    codes.append("persistent_write_requires_approval")

        if self.settings is not None and len(plan.tasks) > self.settings.agent_max_tasks:
            return SafetyDecision(
                allowed=False,
                blocked=True,
                reason_codes=["task_limit_exceeded"],
                safe_message="Plan exceeds the maximum number of tasks.",
            )

        # Optional model assist when deterministic checks pass but request looks unusual.
        ambiguous = bool(
            re.search(r"(?i)\b(bypass|jailbreak|dan\s+mode|unfiltered)\b", user_request or "")
        )
        if ambiguous and self.llm_service is not None:
            assisted = await self._model_review(user_request, plan)
            if assisted.blocked:
                return assisted
            codes.extend(assisted.reason_codes)
            requires_approval = requires_approval or assisted.requires_approval

        if requires_approval and "persistent_write_requires_approval" not in codes:
            codes.append("persistent_write_requires_approval")

        return SafetyDecision(
            allowed=True,
            blocked=False,
            requires_approval=requires_approval,
            reason_codes=list(dict.fromkeys(codes + ["plan_allowed"])),
            safe_message="Plan passed safety checks",
        )

    async def _model_review(self, user_request: str, plan: AgentPlan) -> SafetyDecision:
        assert self.llm_service is not None
        try:
            response = await self.llm_service.generate(
                GenerateRequest(
                    messages=[
                        ChatMessage(
                            role=MessageRole.system,
                            content=(
                                "You are the Safety Agent. Return JSON with keys: "
                                "allowed, blocked, requires_approval, reason_codes, safe_message. "
                                "Prefer allow unless clearly unsafe. Never rewrite user intent."
                            ),
                        ),
                        ChatMessage(
                            role=MessageRole.user,
                            content=(
                                f"Request: {user_request[:800]}\n"
                                f"Plan agents: {[t.agent_name for t in plan.tasks]}"
                            ),
                        ),
                    ],
                    temperature=0.0,
                    max_tokens=250,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "safety_model_assist_failed error_code=%s",
                type(exc).__name__,
            )
            # Fail closed on ambiguous model-assist failure.
            return SafetyDecision(
                allowed=False,
                blocked=True,
                reason_codes=["safety_provider_failure"],
                safe_message="Safety review could not be completed safely.",
            )
        data = load_json_object(response.content or "")
        if not data:
            return SafetyDecision(
                allowed=False,
                blocked=True,
                reason_codes=["safety_malformed_output"],
                safe_message="Safety review could not be completed safely.",
            )
        blocked = bool(data.get("blocked"))
        allowed = bool(data.get("allowed", not blocked))
        raw_codes = data.get("reason_codes")
        codes: list[Any] = raw_codes if isinstance(raw_codes, list) else []
        return SafetyDecision(
            allowed=allowed and not blocked,
            blocked=blocked or not allowed,
            requires_approval=bool(data.get("requires_approval")),
            reason_codes=[str(c)[:64] for c in codes][:16] or ["model_assisted_safety"],
            safe_message=str(data.get("safe_message") or "")[:500],
        )
