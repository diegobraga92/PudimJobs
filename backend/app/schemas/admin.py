import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SourceHealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    health: str
    last_scraped: datetime | None
    rate_limit_seconds: int


class StatsResponse(BaseModel):
    sources: int
    jobs: int
    jobs_last_24h: int
    failed_runs: int
    total_runs: int


class ScrapeRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    status: str
    new_jobs: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class ReplayResponse(BaseModel):
    replayed: bool
    run_id: uuid.UUID
    source_id: uuid.UUID
