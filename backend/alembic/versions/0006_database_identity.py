"""Phase 5.1 database identity metadata.

Revision ID: 0006_database_identity
Revises: 0005_password_reset
Create Date: 2026-07-29

Notes:
- Stores durable application/database identity so readiness can fail when the
  backend is pointed at an unrelated Cortexa database.
- Seeds the local development identity (cortexa-agent-development). Non-dev
  environments must update application_metadata.database_identity to match
  EXPECTED_DATABASE_IDENTITY after migrate (Alembic runs this revision once).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_database_identity"
down_revision: str | None = "0005_password_reset"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED = (
    ("application_id", "cortexa-ai-agent-platform"),
    ("database_identity", "cortexa-agent-development"),
    ("schema_generation", "0006_database_identity"),
    ("created_by_project", "cortexa"),
)


def upgrade() -> None:
    op.create_table(
        "application_metadata",
        sa.Column("key", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    metadata = sa.table(
        "application_metadata",
        sa.column("key", sa.String),
        sa.column("value", sa.String),
    )
    op.bulk_insert(
        metadata,
        [{"key": key, "value": value} for key, value in _SEED],
    )


def downgrade() -> None:
    op.drop_table("application_metadata")
