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
    respect_robots_txt: bool = True


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=1, max_length=1024)
    type: SourceType | None = None
    config: dict | None = None
    rate_limit_seconds: int | None = Field(default=None, ge=0, le=86400)
    respect_robots_txt: bool | None = None


class SourceResponse(SourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    health: SourceHealth
    last_scraped: datetime | None
    created_at: datetime
    jobs_count: int = 0


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
