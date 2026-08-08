import uuid
from datetime import datetime

from pydantic import BaseModel


class GeneratedCVResponse(BaseModel):
    id: uuid.UUID
    master_cv_id: uuid.UUID | None
    job_id: uuid.UUID | None
    job_title: str | None
    job_company: str | None
    created_at: datetime


class TailorRequest(BaseModel):
    cv_id: uuid.UUID | None = None
