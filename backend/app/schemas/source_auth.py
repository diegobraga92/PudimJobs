"""Schemas for per-source authentication."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import SourceAuthType


class SourceAuthUpdate(BaseModel):
    auth_type: SourceAuthType = SourceAuthType.none
    token: str | None = Field(default=None, max_length=2048)  # write-only
    api_key: str | None = Field(default=None, max_length=2048)  # write-only


class SourceAuthResponse(BaseModel):
    auth_type: SourceAuthType
    has_auth: bool
    updated_at: datetime | None = None
