"""Regression contracts for Phase 10.2 observability."""

from pathlib import Path


def test_analytics_exposes_ai_observability_metrics() -> None:
    source = Path("app/admin/service.py").read_text()
    for metric in (
        '"rag_queries"',
        '"successful_responses"',
        '"failed_responses"',
        '"no_answer_responses"',
        '"citation_count"',
        '"total_tokens"',
        '"retrieval_latency_ms"',
        '"generation_latency_ms"',
        '"first_token_latency_ms"',
    ):
        assert metric in source


def test_no_context_path_persists_safe_timing_only() -> None:
    source = Path("app/services/chat.py").read_text()
    assert '"observability": {"outcome": "no_answer", "safe": True}' in source
    assert '"rag_timing"' in source
