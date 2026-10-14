"""Clear removed cookie-based source credentials.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-13
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE source_auth "
        "SET auth_type = 'none', credentials_encrypted = NULL "
        "WHERE auth_type = 'cookies'"
    )


def downgrade() -> None:
    # Irreversible: cleared cookie credentials are discarded, not recoverable.
    pass
