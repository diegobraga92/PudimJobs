import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import CVVariant
from app.schemas.master_cv import CVStructure


class GeneratedCVResponse(BaseModel):
    """A tailored CV artifact (ADR 016)."""

    id: uuid.UUID
    job_id: uuid.UUID | None
    job_title: str | None
    job_company: str | None
    source_master_cv_id: uuid.UUID | None
    variant: CVVariant
    created_at: datetime
    updated_at: datetime
    structured_json: dict | None = None
    ats_score: int | None = None
    ats_report: dict | None = None


class GeneratedCVUpdate(BaseModel):
    """Edit a tailored CV in place (re-renders the PDF, clears the ATS cache)."""

    structured_json: CVStructure


class TailorRequest(BaseModel):
    cv_id: uuid.UUID | None = None
    # When set, the application is pointed at the deterministic (``rule``) variant
    # once the task completes (answers "which CV did I send for this
    # application?"). The optional ``llm`` variant is only linked when the user
    # explicitly picks it (see ADR 016).
    application_id: uuid.UUID | None = None

