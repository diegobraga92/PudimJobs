"""Add ``sources.avoided_at``/``avoid_reason`` for soft-avoiding a source (ADR 019).

An avoided source is never fetched and never reminded about, but stays listed so
it remains a visible reminder the user can restore later.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-15
"""

import sqlalchemy as sa

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources", sa.Column("avoided_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("sources", sa.Column("avoid_reason", sa.String(length=280), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "avoid_reason")
    op.drop_column("sources", "avoided_at")
