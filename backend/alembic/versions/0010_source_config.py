"""Add the ``sources.config`` JSONB column (adapter settings).

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("config", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sources", "config")
