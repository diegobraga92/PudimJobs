"""Add ``sources.respect_robots_txt`` (per-source scraping ethics toggle).

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-13
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column(
            "respect_robots_txt",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("sources", "respect_robots_txt")
