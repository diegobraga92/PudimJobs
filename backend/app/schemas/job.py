import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    description: str | None = None
    url: str | None = Field(default=None, max_length=1024)
    source_id: uuid.UUID | None = None
    posted_date: date | None = None
    tags: list[str] = Field(default_factory=list)


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    company: str | None = Field(default=None, min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    description: str | None = None
    url: str | None = Field(default=None, max_length=1024)
    source_id: uuid.UUID | None = None
    posted_date: date | None = None
    tags: list[str] | None = None
    hidden: bool | None = None


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    company: str
    location: str | None = None
    url: str | None
    posted_date: date | None
    tags: list[str]
    hidden: bool = False
    created_at: datetime
    score: float = 0.0


class JobResponse(JobSummary):
    description: str | None
    source_id: uuid.UUID | None


class JobCleanupRequest(BaseModel):
    """Criteria for the bulk jobs cleanup (ADR 023).

    At least one of ``older_than_days`` / ``source_id`` must be given; both may
    be combined (``AND``). ``dry_run`` is the default because a bulk delete also
    cascades away the applications attached to the matched jobs.
    """

    # Matched against ``Job.created_at`` (the moment the job entered the DB), not
    # ``posted_date``: the posting date is nullable and often absent on scraped
    # rows, so an age filter on it would silently spare whole sources.
    older_than_days: int | None = Field(default=None, ge=1, le=3650)
    source_id: uuid.UUID | None = None
    # Jobs already tracked in the pipeline (they have an application) are kept
    # unless the caller explicitly opts in — deleting them cascades the
    # application away (``applications.job_id`` is ON DELETE CASCADE).
    include_with_applications: bool = False
    dry_run: bool = True


class JobCleanupResponse(BaseModel):
    """What a cleanup run matched, deleted and deliberately spared (ADR 023)."""

    matched: int
    deleted: int
    protected: int
    dry_run: bool


class JobImportRequest(BaseModel):
    """The posting URL the user pasted into the Add-job dialog (ADR 025)."""

    url: str = Field(min_length=1, max_length=1024)


class JobImportPreview(BaseModel):
    """A draft extracted from one posting URL — nothing has been saved (ADR 025).

    Every field is what the review form should be pre-filled with; the user edits
    it and the normal ``POST /api/jobs`` persists it. ``extraction`` says which
    strategy produced the values, ``llm_used`` whether the optional LLM gap-fill
    ran, and ``warnings`` what the user should double-check. A fetch that never
    produced a page comes back as ``error`` (HTTP 200), so the form can explain
    the failure without losing whatever the user already typed.
    """

    fetched_url: str
    status_code: int | None = None
    url: str | None = None
    title: str = ""
    company: str = ""
    location: str | None = None
    description: str | None = None
    posted_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    #: ``json_ld`` (schema.org metadata), ``css`` (heuristic selectors), ``llm``
    #: (only the LLM found anything) or ``none`` (nothing readable on the page).
    extraction: Literal["json_ld", "css", "llm", "none"] = "none"
    llm_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    #: Set when the current user already saved a job with this URL.
    existing_job_id: uuid.UUID | None = None
    error: str | None = None

