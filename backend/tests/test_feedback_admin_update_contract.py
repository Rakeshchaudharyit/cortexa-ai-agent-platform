from pathlib import Path


def test_admin_feedback_update_reloads_joined_context_after_commit() -> None:
    source = Path("backend/app/api/routes/admin/feedback.py").read_text()
    assert "await session.commit()" in source
    assert "select(MessageFeedback, Message, User)" in source
    assert ".where(MessageFeedback.id == feedback_id)" in source
    assert "saved_feedback, message, user = row" in source
    assert "citation_count=len(message.citations or [])" in source
