"""Drop the never-populated ``jobs.raw_html`` column; add ``jobs.external_id``.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("jobs", "raw_html")
    op.add_column(
        "jobs",
        sa.Column("external_id", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_jobs_source_external_id", "jobs", ["source_id", "external_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_jobs_source_external_id", "jobs", type_="unique")
    op.drop_column("jobs", "external_id")
    op.add_column(
        "jobs",
        sa.Column("raw_html", sa.Text(), nullable=True),
    )
