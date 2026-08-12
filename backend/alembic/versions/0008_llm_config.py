"""Add the global ``llm_config`` single-row table.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_ROW_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "llm_config",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(length=255), nullable=False, server_default="https://api.openai.com/v1"),
        sa.Column("model", sa.String(length=64), nullable=False, server_default="gpt-4o-mini"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Seed the single config row so the admin UI always has something to read.
    op.execute(
        f"INSERT INTO llm_config (id, enabled, base_url, model) VALUES "
        f"('{_ROW_ID}', false, 'https://api.openai.com/v1', 'gpt-4o-mini')"
    )


def downgrade() -> None:
    op.drop_table("llm_config")
