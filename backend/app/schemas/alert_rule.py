import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AlertRuleBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    keywords: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    remote_only: bool = False
    min_years_experience: int | None = Field(default=None, ge=0, le=50)
    channels: list[str] = Field(default_factory=lambda: ["in_app"])


class AlertRuleCreate(AlertRuleBase):
    pass


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    keywords: list[str] | None = None
    companies: list[str] | None = None
    tags: list[str] | None = None
    remote_only: bool | None = None
    min_years_experience: int | None = Field(default=None, ge=0, le=50)
    channels: list[str] | None = None
    active: bool | None = None


class AlertRuleResponse(AlertRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    active: bool
    created_at: datetime
