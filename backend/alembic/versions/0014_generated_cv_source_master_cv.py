"""Add ``generated_cvs.source_master_cv_id`` for tailoring idempotency.

``generated_cvs.master_cv_id`` points at the *generated* CV version; the new
column records the *source* master-CV version a tailored artifact came from, so
re-tailoring the same job against the same source CV is idempotent.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generated_cvs",
        sa.Column("source_master_cv_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_generated_cvs_source_master_cv_id",
        "generated_cvs",
        ["source_master_cv_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_generated_cvs_source_master_cv_id", table_name="generated_cvs")
    op.drop_column("generated_cvs", "source_master_cv_id")
