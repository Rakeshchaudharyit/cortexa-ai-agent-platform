"""Authentication schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole, UserStatus


def normalize_email(value: str) -> str:
    """Trim and lowercase email for storage and lookup."""
    return value.strip().lower()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)
    full_name: str = Field(min_length=1, max_length=200)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_register_email(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_email(value)
        return value

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("full_name cannot be blank")
        return name


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_login_email(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_email(value)
        return value


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    status: UserStatus
    is_email_verified: bool
    created_at: datetime
    last_login_at: datetime | None = None


class AuthTokenResponse(BaseModel):
    user: UserPublic
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    access_token_expires_at: datetime


class MessageResponse(BaseModel):
    message: str
