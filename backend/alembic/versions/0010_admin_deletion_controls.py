"""Phase 8.1 admin deletion controls.

Revision ID: 0010_admin_deletion_controls
Revises: 0009_enterprise_admin
Create Date: 2026-08-01

Notes:
- Makes tool_executions.user_id nullable with ON DELETE SET NULL so
  permanent user deletion can anonymize governance records instead of
  cascading them away with the user row.
- Does not add soft-delete columns for conversations/documents (hard delete
  remains explicit) or allow deletion of admin_audit_events.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_admin_deletion_controls"
down_revision: str | None = "0009_enterprise_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("tool_executions_user_id_fkey", "tool_executions", type_="foreignkey")
    op.alter_column(
        "tool_executions",
        "user_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.create_foreign_key(
        "tool_executions_user_id_fkey",
        "tool_executions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Refuse downgrade when anonymized rows exist — restoring NOT NULL would fail.
    bind = op.get_bind()
    null_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM tool_executions WHERE user_id IS NULL")
    ).scalar()
    if int(null_count or 0) > 0:
        raise RuntimeError(
            "Cannot downgrade 0010_admin_deletion_controls while anonymized "
            "tool_executions rows (user_id IS NULL) exist"
        )
    op.drop_constraint("tool_executions_user_id_fkey", "tool_executions", type_="foreignkey")
    op.alter_column(
        "tool_executions",
        "user_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.create_foreign_key(
        "tool_executions_user_id_fkey",
        "tool_executions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
