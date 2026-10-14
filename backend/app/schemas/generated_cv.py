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


class TailorResponse(BaseModel):
    """Acknowledgement of an enqueued tailor run (ADR 016).

    ``variants`` names the artifacts the run will produce — ``rule`` always, plus
    ``llm`` when the LLM is enabled with a usable key. The client polls until the
    expected set has landed, so it can tell a finished single-variant run from one
    whose AI rewrite is still being written.
    """

    enqueued: bool
    job_id: uuid.UUID
    cv_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    variants: list[CVVariant]


class TailorRequest(BaseModel):
    cv_id: uuid.UUID | None = None
    # When set, the application is pointed at the deterministic (``rule``) variant
    # once the task completes (answers "which CV did I send for this
    # application?"). The optional ``llm`` variant is only linked when the user
    # explicitly picks it (see ADR 016).
    application_id: uuid.UUID | None = None

