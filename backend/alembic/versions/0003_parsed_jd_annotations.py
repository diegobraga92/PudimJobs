"""Add jobs.parsed_jd and master_cv.annotations.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("parsed_jd", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "master_cv",
        sa.Column("annotations", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("master_cv", "annotations")
    op.drop_column("jobs", "parsed_jd")
