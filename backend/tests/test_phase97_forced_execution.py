"""Phase 9.7 forced orchestration contract tests."""

from app.agents.coordinator import CoordinatorEngine
from app.conversations.schemas import CreateMessageRequest


def test_message_request_defaults_to_normal_chat_contract() -> None:
    request = CreateMessageRequest(content="Hello")
    assert request.force_multi_agent is False
    assert request.execution_profile == "fast"


def test_message_request_accepts_explicit_deep_orchestration() -> None:
    request = CreateMessageRequest(
        content="Coordinate a technical review",
        force_multi_agent=True,
        execution_profile="deep",
    )
    assert request.force_multi_agent is True
    assert request.execution_profile == "deep"


def test_execution_profiles_have_bounded_distinct_limits() -> None:
    assert CoordinatorEngine._profile_limits("fast") == (90, 35, 20, False)
    assert CoordinatorEngine._profile_limits("balanced") == (150, 60, 30, True)
    assert CoordinatorEngine._profile_limits("deep") == (240, 90, 45, True)
    assert CoordinatorEngine._profile_limits("unknown") == (90, 35, 20, False)
