"""Add per-source scrape cadence to ``sources``.

``NULL`` keeps the previous behaviour (the global sweep freshness); the column
lets a source (notably a paid search provider) run less often to save credits.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-17
"""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("scrape_interval_minutes", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sources", "scrape_interval_minutes")
