"""Schemas for per-source authentication.

Credentials (bearer token / API key) are write-only fields: they are encrypted
on write and never included in responses.
"""

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
