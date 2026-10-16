import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    description: str | None = None
    url: str | None = Field(default=None, max_length=1024)
    source_id: uuid.UUID | None = None
    posted_date: date | None = None
    tags: list[str] = Field(default_factory=list)


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    company: str | None = Field(default=None, min_length=1, max_length=255)
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
