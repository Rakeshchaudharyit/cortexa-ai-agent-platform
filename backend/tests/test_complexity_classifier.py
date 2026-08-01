"""Phase 9.2 complexity classifier tests."""

from __future__ import annotations

import pytest
from app.agents.classifier import ComplexityClassifier
from app.agents.schemas import ClassifierInput
from app.core.config import Settings
from app.services.llm import LLMService

from tests.fakes.llm import FakeLLMProvider


def _classifier(settings: Settings, llm: FakeLLMProvider | None = None) -> ComplexityClassifier:
    llm_service = LLMService(settings=settings, provider=llm) if llm is not None else None
    return ComplexityClassifier(settings, llm_service=llm_service)


def test_greeting_is_single_agent(settings: Settings) -> None:
    decision = _classifier(settings).classify_deterministic(ClassifierInput(user_message="Hello!"))
    assert decision.execution_mode == "single_agent"
    assert "greeting" in decision.reason_codes


def test_explanation_is_single_agent(settings: Settings) -> None:
    decision = _classifier(settings).classify_deterministic(
        ClassifierInput(user_message="Explain FastAPI in two sentences.")
    )
    assert decision.execution_mode == "single_agent"
    assert "simple_explanation" in decision.reason_codes


def test_rewrite_is_single_agent(settings: Settings) -> None:
    decision = _classifier(settings).classify_deterministic(
        ClassifierInput(user_message="Rewrite this paragraph to be clearer: Hello world.")
    )
    assert decision.execution_mode == "single_agent"
    assert "simple_rewrite" in decision.reason_codes


def test_single_calculator_is_single_agent(settings: Settings) -> None:
    decision = _classifier(settings).classify_deterministic(
        ClassifierInput(user_message="What is 245 × 17?")
    )
    assert decision.execution_mode == "single_agent"
    assert "simple_calculator" in decision.reason_codes


def test_single_datetime_is_single_agent(settings: Settings) -> None:
    decision = _classifier(settings).classify_deterministic(
        ClassifierInput(user_message="What is the current time in Asia/Kolkata?")
    )
    assert decision.execution_mode == "single_agent"
    assert "simple_datetime" in decision.reason_codes


def test_single_document_lookup_is_single_agent(settings: Settings) -> None:
    decision = _classifier(settings).classify_deterministic(
        ClassifierInput(
            user_message="What is the project codename in this selected document?",
            conversation_mode="document",
            selected_document_ids=["11111111-1111-1111-1111-111111111111"],
        )
    )
    assert decision.execution_mode == "single_agent"
    assert "simple_document_lookup" in decision.reason_codes


def test_direct_memory_lookup_is_single_agent(settings: Settings) -> None:
    decision = _classifier(settings).classify_deterministic(
        ClassifierInput(
            user_message="What do you remember about my preferences?",
            memory_enabled=True,
        )
    )
    assert decision.execution_mode == "single_agent"
    assert "simple_memory_lookup" in decision.reason_codes


def test_document_calc_recommend_is_multi_agent(settings: Settings) -> None:
    decision = _classifier(settings).classify_deterministic(
        ClassifierInput(
            user_message=(
                "Review the selected contract, identify risks, calculate a 15 percent "
                "contingency, and prepare a recommendation."
            ),
            conversation_mode="document",
            selected_document_ids=["11111111-1111-1111-1111-111111111111"],
        )
    )
    assert decision.execution_mode == "multi_agent"
    assert decision.requires_planning is True


def test_memory_document_synthesis_is_multi_agent(settings: Settings) -> None:
    decision = _classifier(settings).classify_deterministic(
        ClassifierInput(
            user_message=(
                "Use my saved preferences and this document to draft a revised proposal "
                "and remember the final decision."
            ),
            conversation_mode="document",
            selected_document_ids=["11111111-1111-1111-1111-111111111111"],
            memory_enabled=True,
        )
    )
    assert decision.execution_mode == "multi_agent"


def test_message_length_alone_does_not_trigger_multi_agent(settings: Settings) -> None:
    long_text = "Please explain recursion carefully. " * 40
    decision = _classifier(settings).classify_deterministic(ClassifierInput(user_message=long_text))
    assert decision.execution_mode == "single_agent"
    assert "long_message_ignored_for_routing" in decision.reason_codes


@pytest.mark.asyncio
async def test_ambiguous_classifier_provider_failure_falls_back(settings: Settings) -> None:
    llm = FakeLLMProvider(fail_mode="timeout")
    classifier = _classifier(settings, llm)
    # Force ambiguous path by crafting a baseline then calling model assist via classify.
    baseline = classifier.classify_deterministic(
        ClassifierInput(
            user_message="Do the thing with the pieces and also the other steps somehow.",
            selected_tool_intent=[],
        )
    )
    # Manually invoke model path with ambiguous baseline.
    baseline.reason_codes = list(dict.fromkeys([*baseline.reason_codes, "ambiguous"]))
    baseline.confidence = 0.55
    result = await classifier._classify_with_model(
        ClassifierInput(user_message="Ambiguous multi-step request somehow"),
        baseline,
    )
    assert result.execution_mode == "single_agent"
    assert "classifier_provider_failure" in result.reason_codes
