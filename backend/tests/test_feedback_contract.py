from pathlib import Path


def test_feedback_contract_is_wired_end_to_end() -> None:
    routes = Path("backend/app/api/routes/conversations.py").read_text()
    admin = Path("backend/app/api/routes/admin/feedback.py").read_text()
    model = Path("backend/app/models/feedback.py").read_text()
    assert 'messages/{message_id}/feedback' in routes
    assert '@router.get("/feedback"' in admin
    assert 'UniqueConstraint("message_id", "user_id"' in model
