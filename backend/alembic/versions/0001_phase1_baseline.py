"""Initial empty schema baseline — no business-domain tables in Phase 1.

Revision ID: 0001_phase1_baseline
Revises:
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_phase1_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Phase 1: empty metadata only. Domain tables arrive in later phases.
    pass


def downgrade() -> None:
    pass
