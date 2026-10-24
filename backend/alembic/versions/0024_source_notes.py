"""Add a per-source free-form ``notes`` column (any source type).

Notes used to live in ``config.notes`` and only for ``manual`` (watchlist)
sources; that made a human-only field part of the scraper contract and kept
every other type from carrying one. This moves them to their own column so no
scraper has to know about them and the edit form can expose the same field
everywhere.

Existing ``config.notes`` values are moved over and the key is dropped:
``config`` is what drives the scraper, and a leftover duplicate would be the
kind of two-sources-of-truth bug this migration exists to remove. Only the
lookup is data-dependent; the rest is DDL.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-24
"""

import sqlalchemy as sa

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("notes", sa.Text(), nullable=True))
    # Copy whatever the old manual-only field held, trimming it like the API
    # now does (blank becomes NULL, not an empty string).
    op.execute(
        """
        UPDATE sources
        SET notes = NULLIF(BTRIM(config ->> 'notes'), '')
        WHERE config ? 'notes'
        """
    )
    op.execute(
        """
        UPDATE sources
        SET config = config - 'notes'
        WHERE config ? 'notes'
        """
    )


def downgrade() -> None:
    # Restore the old shape before the column disappears, so nothing is lost.
    op.execute(
        """
        UPDATE sources
        SET config = COALESCE(config, '{}'::jsonb) || jsonb_build_object('notes', notes)
        WHERE notes IS NOT NULL
        """
    )
    op.drop_column("sources", "notes")
