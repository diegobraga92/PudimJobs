import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import ApplicationStatus


class ApplicationCreate(BaseModel):
    job_id: uuid.UUID
    status: ApplicationStatus = ApplicationStatus.saved
    applied_date: date | None = None
    notes: str | None = None
    lessons_learned: str | None = None
    generated_cv_id: uuid.UUID | None = None


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    applied_date: date | None = None
    notes: str | None = None
    lessons_learned: str | None = None
    generated_cv_id: uuid.UUID | None = None


class ApplicationResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    status: ApplicationStatus
    applied_date: date | None
    notes: str | None
    lessons_learned: str | None
    generated_cv_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    job_title: str
    job_company: str
    job_url: str | None


class ApplicationDetail(ApplicationResponse):
    job_description: str | None = None


class LessonEntry(BaseModel):
    """An application's retrospective, joined with its job for display."""

    application_id: uuid.UUID
    job_title: str
    job_company: str
    status: ApplicationStatus
    applied_date: date | None
    lessons_learned: str
    updated_at: datetime
