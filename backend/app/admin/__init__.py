"""Enterprise administration domain package."""

from __future__ import annotations

from app.admin.audit import AdminAuditService, record_admin_action
from app.admin.exceptions import (
    AdminConflictError,
    AdminNotFoundError,
    AdminValidationError,
    LastAdminProtectionError,
)
from app.admin.policies import (
    ADMIN_PAGE_DEFAULT,
    ADMIN_PAGE_MAX,
    SAFE_SETTING_KEYS,
    UNSAFE_SETTING_KEYS,
    is_safe_setting_key,
)
from app.admin.service import AdminService

__all__ = [
    "ADMIN_PAGE_DEFAULT",
    "ADMIN_PAGE_MAX",
    "SAFE_SETTING_KEYS",
    "UNSAFE_SETTING_KEYS",
    "AdminAuditService",
    "AdminConflictError",
    "AdminNotFoundError",
    "AdminService",
    "AdminValidationError",
    "LastAdminProtectionError",
    "is_safe_setting_key",
    "record_admin_action",
]
