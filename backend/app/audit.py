"""Audit logging helper.

Audit entries are written in the same transaction as the mutation they
describe, so the caller commits once and both changes land atomically.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log_audit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None = None,
    changes: dict[str, Any] | None = None,
) -> None:
    """Record an audit event for a mutation performed by ``user_id``."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            changes=changes,
        )
    )
