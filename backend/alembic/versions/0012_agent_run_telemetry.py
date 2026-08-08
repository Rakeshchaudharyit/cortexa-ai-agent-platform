"""Add durable, content-free orchestration telemetry.

Revision ID: 0012_agent_run_telemetry
Revises: 0011_multi_agent_orchestration
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_agent_run_telemetry"
down_revision: str | None = "0011_multi_agent_orchestration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("context_characters_used", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("agent_runs", sa.Column("planning_duration_ms", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("execution_duration_ms", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("synthesis_duration_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "synthesis_duration_ms")
    op.drop_column("agent_runs", "execution_duration_ms")
    op.drop_column("agent_runs", "planning_duration_ms")
    op.drop_column("agent_runs", "context_characters_used")
