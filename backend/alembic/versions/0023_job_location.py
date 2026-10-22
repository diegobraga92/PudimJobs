"""Add a canonical ``jobs.location`` column.

Scrapers used to fold a detected location into ``tags`` or append a
``"• Location: …"`` marker to the description. Neither can drive the per-source
location gate or a location filter in the API, so the detected value now has
its own column (and index for the case-insensitive filter).

Existing rows are intentionally left NULL: backfilling from tags/description
would guess, and a NULL location is the documented "board did not report one"
state (those jobs are always kept by the gate).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-22
"""

import sqlalchemy as sa

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("location", sa.String(length=255), nullable=True))
    op.create_index("ix_jobs_location", "jobs", ["location"])


def downgrade() -> None:
    op.drop_index("ix_jobs_location", table_name="jobs")
    op.drop_column("jobs", "location")
