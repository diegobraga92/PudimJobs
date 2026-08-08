"""Add jobs.search_vector (generated tsvector) + GIN index.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-08
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_SEARCH_VECTOR = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(company, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(description, '')), 'C')"
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE jobs ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_SEARCH_VECTOR}) STORED"
    )
    op.execute(
        "CREATE INDEX ix_jobs_search_vector ON jobs USING GIN (search_vector)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_jobs_search_vector")
    op.execute("ALTER TABLE jobs DROP COLUMN search_vector")
