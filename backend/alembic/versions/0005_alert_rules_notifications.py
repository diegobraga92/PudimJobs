"""Add alert_rules and notifications tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("keywords", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("companies", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("remote_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("min_years_experience", sa.Integer(), nullable=True),
        sa.Column("channels", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_rules_user_id", "alert_rules", ["user_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("alert_rule_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="created"),
        sa.Column("error", sa.String(length=1024), nullable=True),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["alert_rule_id"], ["alert_rules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_alert_rules_user_id", table_name="alert_rules")
    op.drop_table("alert_rules")
