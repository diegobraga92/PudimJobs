"""Add ATS scoring columns to ``generated_cvs``.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-13
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("generated_cvs", sa.Column("ats_score", sa.Integer(), nullable=True))
    op.add_column(
        "generated_cvs",
        sa.Column("ats_report", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generated_cvs", "ats_report")
    op.drop_column("generated_cvs", "ats_score")
