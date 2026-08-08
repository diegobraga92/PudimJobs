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


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    company: str
    url: str | None
    posted_date: date | None
    tags: list[str]
    created_at: datetime
    score: float = 0.0


class JobResponse(JobSummary):
    description: str | None
    source_id: uuid.UUID | None
