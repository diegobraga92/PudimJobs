import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SourceHealth, SourceType


class SourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=1024)
    type: SourceType
    config: dict | None = Field(default=None)
    # Scraping ethics / politeness: cooldown between requests to the domain and
    # whether to honour robots.txt `Disallow` rules.
    rate_limit_seconds: int = Field(default=30, ge=0, le=86400)
    # NULL inherits the global sweep cadence. The largest option is two weeks;
    # longer values are rejected so a typo cannot silently freeze a source.
    scrape_interval_minutes: int | None = Field(default=None, ge=60, le=20160)
    respect_robots_txt: bool = True


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=1, max_length=1024)
    type: SourceType | None = None
    config: dict | None = None
    rate_limit_seconds: int | None = Field(default=None, ge=0, le=86400)
    scrape_interval_minutes: int | None = Field(default=None, ge=60, le=20160)
    respect_robots_txt: bool | None = None
    # Soft-avoid flag (ADR 019): stops fetching/reminders, keeps the source listed.
    avoided: bool | None = None
    avoid_reason: str | None = Field(default=None, max_length=280)


class SourceAvoidRequest(BaseModel):
    """Body of ``POST /api/sources/{id}/avoid`` (ADR 019)."""

    avoided: bool
    reason: str | None = Field(default=None, max_length=280)


class SourceResponse(SourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    health: SourceHealth
    last_scraped: datetime | None
    # Derived schedule fields for automated sources: when the next scrape is
    # due (null until the first run) and whether the next sweep may enqueue one.
    next_scrape_at: datetime | None = None
    scrape_due: bool = False
    created_at: datetime
    jobs_count: int = 0
    # Manual (watchlist) sources only: when the board is next due for a
    # hand-check, and whether it is due right now. ``None``/``False`` for
    # every other source type.
    next_check_at: datetime | None = None
    due: bool = False
    # User intent (any source type): an avoided source is skipped by the sweeper
    # and never reminded about, but stays visible as a reminder (ADR 019).
    avoided: bool = False
    avoided_at: datetime | None = None
    avoid_reason: str | None = None


class SourcePreviewJob(BaseModel):
    """A normalized job as returned by the source preview."""

    title: str
    company: str
    url: str | None = None
    posted_date: date | None = None
    tags: list[str] = Field(default_factory=list)


class SourcePreviewRequest(BaseModel):
    """Ad-hoc preview: try a URL/type/config *before* saving a source."""

    url: str = Field(min_length=1, max_length=1024)
    type: SourceType = SourceType.career_page
    config: dict | None = Field(default=None)


class SourcePreviewResponse(BaseModel):
    """Outcome of a dry run — nothing is persisted and no run is recorded."""

    fetched_url: str
    status_code: int | None = None
    jobs_found: int = 0
    sample_jobs: list[SourcePreviewJob] = Field(default_factory=list)
    truncated: bool = False
    error: str | None = None


class SourceImportItem(SourceBase):
    """One source in a bulk import. Credentials are never imported."""


class SourceImportRequest(BaseModel):
    """A catalog to import, as produced by ``scripts/import_sources.py``."""

    sources: list[SourceImportItem] = Field(min_length=1, max_length=200)
    dry_run: bool = False


class SourceImportResult(BaseModel):
    index: int
    status: str  # "created" | "skipped" | "invalid"
    name: str
    url: str
    source_id: uuid.UUID | None = None
    reason: str | None = None


class SourceImportResponse(BaseModel):
    created: int
    skipped: int
    invalid: int
    results: list[SourceImportResult] = Field(default_factory=list)
