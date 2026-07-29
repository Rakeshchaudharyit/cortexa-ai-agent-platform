"""Shared database enums for authentication and users."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Role foundation — admin capabilities arrive in a later phase."""

    user = "user"
    admin = "admin"


class UserStatus(StrEnum):
    """Account status controls enforced server-side."""

    active = "active"
    disabled = "disabled"
