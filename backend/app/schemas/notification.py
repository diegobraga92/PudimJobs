import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID | None
    channel: str
    title: str
    message: str | None
    status: str
    read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    total: int
    unread: int
    items: list[NotificationResponse]
