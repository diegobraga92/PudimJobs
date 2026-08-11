import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SourceHealth, SourceType


class SourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=1024)
    type: SourceType


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=1, max_length=1024)
    type: SourceType | None = None


class SourceResponse(SourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    health: SourceHealth
    last_scraped: datetime | None
    created_at: datetime
    jobs_count: int = 0
