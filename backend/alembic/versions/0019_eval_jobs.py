"""Queue-backed evaluation and export jobs.

Revision ID: 0019_eval_jobs
Revises: 0018_document_jobs
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_eval_jobs"
down_revision: str | None = "0018_document_jobs"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rag_evaluation_runs", sa.Column("background_job_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_rag_evaluation_runs_background_job_id", "rag_evaluation_runs", "background_jobs",
        ["background_job_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_rag_evaluation_runs_background_job_id", "rag_evaluation_runs", ["background_job_id"])


def downgrade() -> None:
    op.drop_index("ix_rag_evaluation_runs_background_job_id", table_name="rag_evaluation_runs")
    op.drop_constraint("fk_rag_evaluation_runs_background_job_id", "rag_evaluation_runs", type_="foreignkey")
    op.drop_column("rag_evaluation_runs", "background_job_id")
