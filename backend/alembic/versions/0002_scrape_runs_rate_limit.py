"""Add scrape_runs table and sources.rate_limit_seconds.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-08
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("rate_limit_seconds", sa.Integer(), nullable=False, server_default="30"),
    )
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("new_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(length=1024), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scrape_runs_source_id", "scrape_runs", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_scrape_runs_source_id", table_name="scrape_runs")
    op.drop_table("scrape_runs")
    op.drop_column("sources", "rate_limit_seconds")
