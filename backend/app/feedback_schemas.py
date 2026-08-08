"""Schemas for response feedback and admin review."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

FeedbackSentiment = Literal["helpful", "not_helpful"]
FeedbackReason = Literal[
    "incorrect",
    "missing_source",
    "not_relevant",
    "incomplete",
    "unclear",
    "other",
]
FeedbackStatus = Literal["open", "reviewed", "resolved"]


class MessageFeedbackRequest(BaseModel):
    sentiment: FeedbackSentiment
    reason: FeedbackReason | None = None
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("comment")
    @classmethod
    def clean_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class MessageFeedbackView(BaseModel):
    id: uuid.UUID
    sentiment: FeedbackSentiment
    reason: FeedbackReason | None = None
    comment: str | None = None
    status: FeedbackStatus
    created_at: datetime
    updated_at: datetime


class AdminFeedbackUpdate(BaseModel):
    status: FeedbackStatus
    admin_note: str | None = Field(default=None, max_length=2000)


class AdminFeedbackItem(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    sentiment: FeedbackSentiment
    reason: FeedbackReason | None = None
    comment: str | None = None
    status: FeedbackStatus
    model: str | None = None
    provider: str | None = None
    grounded: bool | None = None
    citation_count: int = 0
    answer_excerpt: str
    admin_note: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AdminFeedbackList(BaseModel):
    items: list[AdminFeedbackItem]
    total: int
    open_count: int
    helpful_count: int
    not_helpful_count: int
