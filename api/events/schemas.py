"""Event schemas.

Versioning contract (see ``CHANGELOG.md``):
- ``version`` is a monotonically increasing integer.
- New fields MUST be additive (optional, with a sensible default) so that
  consumers of older versions can still parse newer payloads.
- Deprecated fields keep their default for two versions before removal.
"""

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
