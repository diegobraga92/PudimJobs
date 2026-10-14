"""Add ``jobs.hidden`` flag for soft-dismissing jobs from the list.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-15
"""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("jobs", "hidden")
