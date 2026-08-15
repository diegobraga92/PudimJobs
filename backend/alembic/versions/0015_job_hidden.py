"""Add ``jobs.hidden`` flag for soft-dismissing jobs from the list.

Jobs the user marks as "not interesting" (or that they already applied to)
are soft-hidden behind this flag instead of being deleted, so the listing
stays clean while the record (and its applications) is preserved.

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
