from types import SimpleNamespace

from app.evaluations.service import score_case


def _case(**overrides):
    values = {
        "expected_keywords_json": ["fastapi", "postgresql"],
        "expected_document_ids_json": ["11111111-1111-1111-1111-111111111111"],
        "should_answer": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_grounded_answer_with_keywords_and_expected_citation_passes():
    result = score_case(
        _case(),
        answer="The platform uses FastAPI and PostgreSQL [1].",
        grounded=True,
        citation_document_ids={"11111111-1111-1111-1111-111111111111"},
        citation_count=1,
    )
    assert result.passed is True
    assert result.overall == 1.0


def test_no_answer_case_requires_ungrounded_response_without_citations():
    result = score_case(
        _case(expected_keywords_json=[], expected_document_ids_json=[], should_answer=False),
        answer="I couldn’t find that information in the selected documents.",
        grounded=False,
        citation_document_ids=set(),
        citation_count=0,
    )
    assert result.passed is True
    assert result.answerability == 1.0


def test_delete_evaluation_case_route_uses_empty_204_response():
    from fastapi import Response

    from app.api.routes.admin.evaluations import router

    route = next(
        item
        for item in router.routes
        if getattr(item, "path", None) == "/evaluations/cases/{case_id}"
        and "DELETE" in getattr(item, "methods", set())
    )
    assert route.status_code == 204
    assert route.response_class is Response


def test_create_evaluation_case_validates_selected_owner_exists():
    import inspect

    from app.api.routes.admin.evaluations import create_case

    source = inspect.getsource(create_case)
    assert "session.get(User, body.owner_user_id)" in source
    assert "evaluation_owner_not_found" in source
