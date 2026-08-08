"""Add scrape_quality table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scrape_quality",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("completeness_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("normalized_company", sa.String(length=255), nullable=True),
        sa.Column("normalized_title", sa.String(length=255), nullable=True),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("canonical_job_id", sa.Uuid(), nullable=True),
        sa.Column("issues", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["canonical_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_scrape_quality_job"),
    )
    op.create_index("ix_scrape_quality_job_id", "scrape_quality", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_scrape_quality_job_id", table_name="scrape_quality")
    op.drop_table("scrape_quality")
