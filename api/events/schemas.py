"""Event schemas."""

import uuid
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field


class JobNewEvent(BaseModel):
    """Published whenever a scraper stores a brand-new job."""

    version: int = Field(default=1, description="Event schema version")
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    job_id: uuid.UUID
    source_id: uuid.UUID
    title: str
    company: str
    url: str | None = None
    posted_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
