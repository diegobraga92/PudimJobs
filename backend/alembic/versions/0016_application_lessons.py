"""Add ``applications.lessons_learned`` retrospective notes.

Free-form text the user writes after an interview round to capture what went
well and what to improve. Surfaced by ``GET /api/applications/lessons`` and the
web "Lessons Learned" page.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-13
"""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("lessons_learned", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "lessons_learned")
