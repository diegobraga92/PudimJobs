"""Add the ``source_auth`` table for per-source login/credentials.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_AUTH_TYPES = ("none", "cookies", "token")


def upgrade() -> None:
    op.create_table(
        "source_auth",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column(
            "auth_type",
            sa.Enum(*_AUTH_TYPES, name="sourceauthtype", native_enum=False),
            nullable=False,
            server_default="none",
        ),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_auth_source_id", "source_auth", ["source_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_source_auth_source_id", table_name="source_auth")
    op.drop_table("source_auth")
    op.execute("DROP TYPE IF EXISTS sourceauthtype")
