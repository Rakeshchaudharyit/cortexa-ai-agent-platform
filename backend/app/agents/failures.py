"""Central failure classification and retry policy for multi-agent execution.

The classifier accepts only exception types, stable error codes, and safe messages.
It must never inspect prompts, retrieved context, tool arguments, or provider payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.agents.exceptions import (
    AgentCancelledError,
    AgentLimitExceededError,
    AgentPlanValidationError,
    AgentSafetyError,
    AgentStateTransitionError,
    AgentTimeoutError,
)


class FailureCategory(StrEnum):
    """Stable operational categories used by orchestration telemetry and policy."""

    transient = "transient"
    permanent = "permanent"
    validation = "validation"
    policy = "policy"
    cancellation = "cancellation"
    timeout = "timeout"
    limit = "limit"
    internal = "internal"


@dataclass(frozen=True, slots=True)
class FailureDecision:
    """Safe retry decision produced from an exception or task result."""

    category: FailureCategory
    error_code: str
    retryable: bool
    safe_message: str
    reason_code: str

    def safe_metadata(self) -> dict[str, str | bool]:
        return {
            "failure_category": self.category.value,
            "error_code": self.error_code,
            "retryable": self.retryable,
            "retry_reason": self.reason_code,
        }


class FailureClassifier:
    """Classify controlled failures consistently across agents and providers."""

    _TRANSIENT_CODES = frozenset(
        {
            "llm_request_timeout",
            "llm_provider_unavailable",
            "provider_unavailable",
            "knowledge_retrieval_failed",
            "memory_retrieval_failed",
            "retrieval_error",
            "tool_timeout",
            "execution_timeout",
            "connection_error",
            "service_unavailable",
            "rate_limited",
        }
    )
    _TIMEOUT_CODES = frozenset(
        {
            "agent_task_timed_out",
            "agent_timed_out",
            "llm_request_timeout",
            "tool_timeout",
            "execution_timeout",
        }
    )
    _VALIDATION_CODES = frozenset(
        {
            "agent_plan_invalid",
            "invalid_arguments",
            "llm_invalid_response",
            "memory_invalid",
            "unsupported_document_type",
            "document_too_large",
            "empty_document",
        }
    )
    _POLICY_CODES = frozenset(
        {
            "agent_safety_rejected",
            "permission_denied",
            "tool_disabled",
            "agent_disabled",
            "confirmation_required",
            "memory_sensitive_content",
        }
    )
    _LIMIT_CODES = frozenset(
        {
            "agent_limit_exceeded",
            "memory_limit_exceeded",
            "result_too_large",
        }
    )
    _CANCELLATION_CODES = frozenset({"agent_cancelled"})
    _PERMANENT_CODES = frozenset(
        {
            "agent_not_found",
            "tool_not_found",
            "document_not_found",
            "memory_not_found",
            "llm_model_unavailable",
            "dependency_failed",
        }
    )

    def classify(
        self,
        *,
        error: BaseException | None = None,
        error_code: str | None = None,
        retryable_hint: bool | None = None,
        safe_message: str | None = None,
    ) -> FailureDecision:
        code = self._normalise_code(error, error_code)
        message = self._safe_message(error, safe_message)

        if isinstance(error, AgentCancelledError) or code in self._CANCELLATION_CODES:
            return self._decision(FailureCategory.cancellation, code, False, message)
        if isinstance(error, (AgentTimeoutError, TimeoutError)) or code in self._TIMEOUT_CODES:
            return self._decision(FailureCategory.timeout, code, True, message)
        if isinstance(error, AgentSafetyError) or code in self._POLICY_CODES:
            return self._decision(FailureCategory.policy, code, False, message)
        if isinstance(error, (AgentPlanValidationError, AgentStateTransitionError)) or code in self._VALIDATION_CODES:
            return self._decision(FailureCategory.validation, code, False, message)
        if isinstance(error, AgentLimitExceededError) or code in self._LIMIT_CODES:
            return self._decision(FailureCategory.limit, code, False, message)
        if code in self._PERMANENT_CODES:
            return self._decision(FailureCategory.permanent, code, False, message)
        if retryable_hint is True or code in self._TRANSIENT_CODES:
            return self._decision(FailureCategory.transient, code, True, message)
        if retryable_hint is False:
            return self._decision(FailureCategory.permanent, code, False, message)
        return self._decision(FailureCategory.internal, code, False, message)

    @staticmethod
    def _normalise_code(error: BaseException | None, error_code: str | None) -> str:
        raw = error_code or getattr(error, "code", None) or (
            type(error).__name__ if error is not None else "agent_task_execution_failed"
        )
        aliases = {
            "LLMRequestTimeoutError": "llm_request_timeout",
            "LLMProviderUnavailableError": "llm_provider_unavailable",
            "LLMModelUnavailableError": "llm_model_unavailable",
            "TimeoutError": "agent_task_timed_out",
        }
        return aliases.get(str(raw), str(raw))

    @staticmethod
    def _safe_message(error: BaseException | None, safe_message: str | None) -> str:
        if safe_message:
            return safe_message[:500]
        candidate = getattr(error, "message", None)
        if isinstance(candidate, str) and candidate:
            return candidate[:500]
        return "The specialist task could not be completed."

    @staticmethod
    def _decision(
        category: FailureCategory,
        code: str,
        retryable: bool,
        message: str,
    ) -> FailureDecision:
        return FailureDecision(
            category=category,
            error_code=code,
            retryable=retryable,
            safe_message=message,
            reason_code=f"{category.value}_{'retry' if retryable else 'stop'}",
        )
