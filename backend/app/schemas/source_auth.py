"""Schemas for per-source authentication.

Credentials (cookies / bearer token) are write-only fields: they are encrypted
on write and never included in responses.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import SourceAuthType


class SourceAuthUpdate(BaseModel):
    auth_type: SourceAuthType = SourceAuthType.none
    cookies: str | None = Field(default=None, max_length=8192)  # write-only
    token: str | None = Field(default=None, max_length=2048)  # write-only


class SourceAuthResponse(BaseModel):
    auth_type: SourceAuthType
    has_auth: bool
    updated_at: datetime | None = None
