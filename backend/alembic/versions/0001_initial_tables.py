"""Initial schema: users, sources, jobs, master_cv, applications, audit_logs.

Revision ID: 0001
Revises:
Create Date: 2026-08-08

The full schema is defined by the ORM models in ``app.models``; this bootstrap
migration materialises ``Base.metadata`` exactly once.
"""

from sqlalchemy.engine import Connection

from alembic import op
from app.database import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    def _create_all(connection: Connection) -> None:
        Base.metadata.create_all(bind=connection)

    async def _run_async(connection) -> None:
        await connection.run_sync(_create_all)

    op.run_async(_run_async)


def downgrade() -> None:
    def _drop_all(connection: Connection) -> None:
        Base.metadata.drop_all(bind=connection)

    async def _run_async(connection) -> None:
        await connection.run_sync(_drop_all)

    op.run_async(_run_async)
