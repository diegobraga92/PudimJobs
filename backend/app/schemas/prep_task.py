import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import PrepCategory, PrepStatus


class PrepTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    category: PrepCategory = PrepCategory.other
    status: PrepStatus = PrepStatus.pending
    due_date: date | None = None
    notes: str | None = None
    job_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None


class PrepTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    category: PrepCategory | None = None
    status: PrepStatus | None = None
    due_date: date | None = None
    notes: str | None = None
    job_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None


class PrepTaskResponse(BaseModel):
    id: uuid.UUID
    title: str
    category: PrepCategory
    status: PrepStatus
    due_date: date | None
    notes: str | None
    job_id: uuid.UUID | None
    application_id: uuid.UUID | None
    job_title: str | None = None
    job_company: str | None = None
    created_at: datetime
    updated_at: datetime
