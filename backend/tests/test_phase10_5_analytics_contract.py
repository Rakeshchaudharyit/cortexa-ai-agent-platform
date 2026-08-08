"""Phase 10.5 enterprise analytics response-contract tests."""

from app.admin.schemas import (
    AdminAnalyticsResponse,
    AdminFeedbackSummary,
    AdminKnowledgeHealth,
    AdminQualitySummary,
)


def test_enterprise_analytics_sections_have_safe_defaults() -> None:
    response = AdminAnalyticsResponse(
        range_days=30,
        points=[],
        totals={},
        generated_at="2026-08-05T00:00:00Z",
    )

    assert response.quality == AdminQualitySummary()
    assert response.knowledge_health == AdminKnowledgeHealth()
    assert response.feedback == AdminFeedbackSummary()
    assert response.top_documents == []
    assert response.top_models == []
    assert response.evaluation_trend == []


def test_quality_summary_accepts_component_scores() -> None:
    quality = AdminQualitySummary(
        score=91.2,
        evaluation_score=94.0,
        feedback_score=90.0,
        success_score=98.0,
        citation_coverage_score=82.0,
        label="Excellent",
    )

    assert quality.score == 91.2
    assert quality.label == "Excellent"
