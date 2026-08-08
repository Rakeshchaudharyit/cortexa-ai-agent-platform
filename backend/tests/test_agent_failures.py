"""Unit tests for centralized multi-agent failure classification."""

from __future__ import annotations

from app.agents.exceptions import AgentCancelledError, AgentLimitExceededError, AgentSafetyError
from app.agents.failures import FailureCategory, FailureClassifier
from app.llm.exceptions import LLMModelUnavailableError, LLMProviderUnavailableError
from app.tools.exceptions import ToolInvalidArgumentsError


def test_provider_unavailable_is_transient_and_retryable() -> None:
    decision = FailureClassifier().classify(error=LLMProviderUnavailableError())
    assert decision.category == FailureCategory.transient
    assert decision.error_code == "llm_provider_unavailable"
    assert decision.retryable is True


def test_model_unavailable_is_permanent() -> None:
    decision = FailureClassifier().classify(error=LLMModelUnavailableError())
    assert decision.category == FailureCategory.permanent
    assert decision.retryable is False


def test_timeout_alias_is_stable() -> None:
    decision = FailureClassifier().classify(error=TimeoutError())
    assert decision.category == FailureCategory.timeout
    assert decision.error_code == "agent_task_timed_out"
    assert decision.retryable is True


def test_validation_failure_does_not_retry() -> None:
    decision = FailureClassifier().classify(error=ToolInvalidArgumentsError())
    assert decision.category == FailureCategory.validation
    assert decision.retryable is False


def test_policy_failure_does_not_retry() -> None:
    decision = FailureClassifier().classify(error=AgentSafetyError("Blocked"))
    assert decision.category == FailureCategory.policy
    assert decision.retryable is False


def test_limit_failure_does_not_retry() -> None:
    decision = FailureClassifier().classify(error=AgentLimitExceededError("Limit"))
    assert decision.category == FailureCategory.limit
    assert decision.retryable is False


def test_cancellation_failure_does_not_retry() -> None:
    decision = FailureClassifier().classify(error=AgentCancelledError())
    assert decision.category == FailureCategory.cancellation
    assert decision.retryable is False


def test_result_retry_hint_is_respected_for_unknown_code() -> None:
    decision = FailureClassifier().classify(
        error_code="custom_connector_busy",
        retryable_hint=True,
        safe_message="Connector temporarily unavailable",
    )
    assert decision.category == FailureCategory.transient
    assert decision.retryable is True
    assert decision.safe_message == "Connector temporarily unavailable"


def test_unknown_failure_defaults_to_non_retryable_internal() -> None:
    decision = FailureClassifier().classify(error_code="unknown_failure")
    assert decision.category == FailureCategory.internal
    assert decision.retryable is False
