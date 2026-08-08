import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    email: str | None
    action: str
    entity_type: str
    entity_id: str | None
    changes: dict | None
    timestamp: datetime
