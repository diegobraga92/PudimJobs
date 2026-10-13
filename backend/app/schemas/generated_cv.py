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
    # The structured CV content behind this artifact (from the linked master CV
    # version), so the UI can edit/preview/export it without a second request.
    structured_json: dict | None = None
    ats_score: int | None = None
    ats_report: dict | None = None


class TailorRequest(BaseModel):
    cv_id: uuid.UUID | None = None
