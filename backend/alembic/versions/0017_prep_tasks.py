"""Create ``prep_tasks`` for tracking interview-preparation checklists.

Each task belongs to a user and may optionally target a job and/or an
application, so a checklist can be scoped per pipeline entry or kept general.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-13
"""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_prep_category = sa.Enum(
    "technical",
    "behavioral",
    "research",
    "logistics",
    "other",
    name="prepcategory",
    native_enum=False,
)
_prep_status = sa.Enum(
    "pending",
    "in_progress",
    "done",
    name="prepstatus",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "prep_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", _prep_category, nullable=False),
        sa.Column("status", _prep_status, nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prep_tasks_user_id", "prep_tasks", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_prep_tasks_user_id", table_name="prep_tasks")
    op.drop_table("prep_tasks")
