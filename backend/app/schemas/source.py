import uuid
from datetime import datetime

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
