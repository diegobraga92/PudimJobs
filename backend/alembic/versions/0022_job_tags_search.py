"""Include tags in ``jobs.search_vector`` and index tags for membership.

Tags carry important signals ("Rust", "Remote") that were invisible to keyword
search, and Postgres' english configuration turns ``c++`` into ``c`` and drops
``go`` as a stopword.  The application adds dedicated predicates for those two
terms; this migration only widens the indexed document.  The GIN index on
``jobs.tags`` backs the case-insensitive tag filter.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-19
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_OLD_EXPR = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(company, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(description, '')), 'C')"
)
_NEW_EXPR = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(company, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(tags::text, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(description, '')), 'C')"
)


def _replace_search_vector(expression: str) -> None:
    op.drop_index("ix_jobs_search_vector", table_name="jobs")
    op.drop_column("jobs", "search_vector")
    op.add_column(
        "jobs",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(expression, persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_jobs_search_vector",
        "jobs",
        ["search_vector"],
        postgresql_using="gin",
    )


def upgrade() -> None:
    _replace_search_vector(_NEW_EXPR)
    op.create_index("ix_jobs_tags", "jobs", ["tags"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_jobs_tags", table_name="jobs")
    _replace_search_vector(_OLD_EXPR)
