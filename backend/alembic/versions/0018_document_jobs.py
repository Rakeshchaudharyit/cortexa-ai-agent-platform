"""Link document ingestion and re-indexing to background jobs.

Revision ID: 0018_document_jobs
Revises: 0017_job_queue
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_document_jobs"
down_revision: str | None = "0017_job_queue"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("background_job_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_documents_background_job_id",
        "documents",
        "background_jobs",
        ["background_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_documents_background_job_id", "documents", ["background_job_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_background_job_id", table_name="documents")
    op.drop_constraint("fk_documents_background_job_id", "documents", type_="foreignkey")
    op.drop_column("documents", "background_job_id")
