"""Admin feedback review queue."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentAdminUser, DbSessionDep
from app.core.exceptions import AppError
from app.feedback_schemas import AdminFeedbackItem, AdminFeedbackList, AdminFeedbackUpdate
from app.models.conversation import Message
from app.models.feedback import MessageFeedback
from app.models.user import User

router = APIRouter()


def _excerpt(value: str, limit: int = 280) -> str:
    cleaned = " ".join(value.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


@router.get("/feedback", response_model=AdminFeedbackList)
async def list_feedback(
    _admin: CurrentAdminUser,
    session: DbSessionDep,
    status_filter: str | None = Query(default=None, alias="status"),
    sentiment: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
) -> AdminFeedbackList:
    filters = []
    if status_filter:
        filters.append(MessageFeedback.status == status_filter)
    if sentiment:
        filters.append(MessageFeedback.sentiment == sentiment)
    rows = (
        await session.execute(
            select(MessageFeedback, Message, User)
            .join(Message, Message.id == MessageFeedback.message_id)
            .join(User, User.id == MessageFeedback.user_id)
            .where(*filters)
            .order_by(MessageFeedback.created_at.desc())
            .limit(limit)
        )
    ).all()
    total = int(await session.scalar(select(func.count()).select_from(MessageFeedback).where(*filters)) or 0)
    open_count = int(await session.scalar(select(func.count()).select_from(MessageFeedback).where(MessageFeedback.status == "open")) or 0)
    helpful_count = int(await session.scalar(select(func.count()).select_from(MessageFeedback).where(MessageFeedback.sentiment == "helpful")) or 0)
    not_helpful_count = int(await session.scalar(select(func.count()).select_from(MessageFeedback).where(MessageFeedback.sentiment == "not_helpful")) or 0)
    items = [
        AdminFeedbackItem(
            id=feedback.id,
            message_id=feedback.message_id,
            conversation_id=feedback.conversation_id,
            user_id=feedback.user_id,
            user_email=user.email,
            sentiment=feedback.sentiment,
            reason=feedback.reason,
            comment=feedback.comment,
            status=feedback.status,
            model=message.model,
            provider=message.provider,
            grounded=message.grounded,
            citation_count=len(message.citations or []),
            answer_excerpt=_excerpt(message.content),
            admin_note=feedback.admin_note,
            reviewed_at=feedback.reviewed_at,
            created_at=feedback.created_at,
            updated_at=feedback.updated_at,
        )
        for feedback, message, user in rows
    ]
    return AdminFeedbackList(
        items=items,
        total=total,
        open_count=open_count,
        helpful_count=helpful_count,
        not_helpful_count=not_helpful_count,
    )


@router.patch("/feedback/{feedback_id}", response_model=AdminFeedbackItem)
async def update_feedback(
    feedback_id: uuid.UUID,
    body: AdminFeedbackUpdate,
    admin: CurrentAdminUser,
    session: DbSessionDep,
) -> AdminFeedbackItem:
    feedback = await session.get(MessageFeedback, feedback_id)
    if feedback is None:
        raise AppError(code="not_found", message="Feedback not found", status_code=404)
    feedback.status = body.status
    feedback.admin_note = body.admin_note.strip() if body.admin_note else None
    feedback.reviewed_by_user_id = admin.id
    feedback.reviewed_at = datetime.now(UTC)
    await session.commit()

    row = (
        await session.execute(
            select(MessageFeedback, Message, User)
            .join(Message, Message.id == MessageFeedback.message_id)
            .join(User, User.id == MessageFeedback.user_id)
            .where(MessageFeedback.id == feedback_id)
        )
    ).one_or_none()
    if row is None:
        raise AppError(code="feedback_context_missing", message="Feedback context is unavailable", status_code=409)

    saved_feedback, message, user = row
    return AdminFeedbackItem(
        id=saved_feedback.id,
        message_id=saved_feedback.message_id,
        conversation_id=saved_feedback.conversation_id,
        user_id=saved_feedback.user_id,
        user_email=user.email,
        sentiment=saved_feedback.sentiment,
        reason=saved_feedback.reason,
        comment=saved_feedback.comment,
        status=saved_feedback.status,
        model=message.model,
        provider=message.provider,
        grounded=message.grounded,
        citation_count=len(message.citations or []),
        answer_excerpt=_excerpt(message.content),
        admin_note=saved_feedback.admin_note,
        reviewed_at=saved_feedback.reviewed_at,
        created_at=saved_feedback.created_at,
        updated_at=saved_feedback.updated_at,
    )
