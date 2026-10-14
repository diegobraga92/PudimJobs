"""Make tailored CVs self-contained artifacts (ADR 016).

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-13
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. New columns on generated_cvs: the content it used to borrow from a
    #    master_cv version, the variant it was produced by, and updated_at.
    op.add_column(
        "generated_cvs",
        sa.Column("variant", sa.String(length=16), nullable=False, server_default="rule"),
    )
    op.add_column(
        "generated_cvs", sa.Column("structured_json", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "generated_cvs",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 2. Backfill the content from the tailored master_cv version each artifact
    #    still points at.
    op.execute(
        """
        UPDATE generated_cvs AS g
        SET structured_json = m.structured_json
        FROM master_cv AS m
        WHERE g.master_cv_id = m.id
        """
    )

    # 3. Collapse any historical duplicates so the new idempotency key can be
    #    enforced by a unique index. Rows with a NULL job/source are untouched
    #    (Postgres treats NULLs as distinct, matching the index semantics).
    op.execute(
        """
        DELETE FROM generated_cvs AS g
        USING generated_cvs AS keep
        WHERE g.user_id = keep.user_id
          AND g.job_id = keep.job_id
          AND g.source_master_cv_id = keep.source_master_cv_id
          AND g.variant = keep.variant
          AND (g.created_at, g.id) < (keep.created_at, keep.id)
        """
    )

    # 4. Applications track the artifact (not a master version) they were sent
    #    with; backfill from the old ``cv_version`` pointer.
    op.add_column("applications", sa.Column("generated_cv_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_applications_generated_cv_id",
        "applications",
        "generated_cvs",
        ["generated_cv_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        UPDATE applications AS a
        SET generated_cv_id = g.id
        FROM generated_cvs AS g
        WHERE a.cv_version = g.master_cv_id
        """
    )

    # 5. Remember which master_cv rows were tailored artifacts before the pointer
    #    goes away, so they can be pruned afterwards.
    op.execute(
        """
        CREATE TEMP TABLE _tailored_master_cv AS
        SELECT DISTINCT master_cv_id AS id
        FROM generated_cvs
        WHERE master_cv_id IS NOT NULL
        """
    )

    op.drop_constraint("applications_cv_version_fkey", "applications", type_="foreignkey")
    op.drop_column("applications", "cv_version")
    op.drop_constraint("generated_cvs_master_cv_id_fkey", "generated_cvs", type_="foreignkey")
    op.drop_column("generated_cvs", "master_cv_id")

    # 6. Delete the now-orphaned tailored master_cv rows. Guarded: never touch a
    #    current version or one still referenced as a tailoring *source*.
    op.execute(
        """
        DELETE FROM master_cv AS m
        WHERE m.id IN (SELECT id FROM _tailored_master_cv)
          AND m.is_current = false
          AND NOT EXISTS (
              SELECT 1 FROM generated_cvs AS g WHERE g.source_master_cv_id = m.id
          )
        """
    )

    # 7. Idempotency: at most one artifact per (user, job, source CV, variant).
    op.create_index(
        "uq_generated_cvs_variant",
        "generated_cvs",
        ["user_id", "job_id", "source_master_cv_id", "variant"],
        unique=True,
    )

    op.execute("DROP TABLE _tailored_master_cv")


def downgrade() -> None:
    op.drop_index("uq_generated_cvs_variant", table_name="generated_cvs")

    # 1. Re-create the tailored master_cv versions so each artifact has a version
    #    again, and point generated_cvs back at it.
    op.add_column("generated_cvs", sa.Column("master_cv_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "generated_cvs_master_cv_id_fkey",
        "generated_cvs",
        "master_cv",
        ["master_cv_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        CREATE TEMP TABLE _downgrade_map AS
        SELECT g.id AS generated_id, g.user_id, g.structured_json
        FROM generated_cvs AS g
        WHERE g.structured_json IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TEMP TABLE _downgrade_versions AS
        SELECT m.generated_id,
               m.user_id,
               COALESCE(
                   (SELECT MAX(version) FROM master_cv WHERE user_id = m.user_id), 0
               ) + ROW_NUMBER() OVER (PARTITION BY m.user_id ORDER BY m.generated_id) AS version
        FROM _downgrade_map AS m
        """
    )
    op.execute(
        """
        INSERT INTO master_cv (id, user_id, label, version, is_current, structured_json)
        SELECT gen_random_uuid(), v.user_id, 'Tailored (restored)', v.version, false,
               m.structured_json
        FROM _downgrade_versions AS v
        JOIN _downgrade_map AS m ON m.generated_id = v.generated_id
        """
    )
    op.execute(
        """
        UPDATE generated_cvs AS g
        SET master_cv_id = mc.id
        FROM _downgrade_versions AS v
        JOIN master_cv AS mc
          ON mc.user_id = v.user_id AND mc.version = v.version
        WHERE g.id = v.generated_id
        """
    )
    op.execute("DROP TABLE _downgrade_versions")
    op.execute("DROP TABLE _downgrade_map")

    # 2. Applications point back at a master CV version.
    op.add_column("applications", sa.Column("cv_version", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "applications_cv_version_fkey",
        "applications",
        "master_cv",
        ["cv_version"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        UPDATE applications AS a
        SET cv_version = g.master_cv_id
        FROM generated_cvs AS g
        WHERE a.generated_cv_id = g.id
        """
    )
    op.drop_constraint("fk_applications_generated_cv_id", "applications", type_="foreignkey")
    op.drop_column("applications", "generated_cv_id")

    # 3. Drop the columns this migration introduced.
    op.drop_column("generated_cvs", "updated_at")
    op.drop_column("generated_cvs", "structured_json")
    op.drop_column("generated_cvs", "variant")
