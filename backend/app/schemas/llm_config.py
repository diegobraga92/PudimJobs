import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LLMConfigUpdate(BaseModel):
    """Admin updates for the global LLM config.

    ``api_key`` is write-only: it is encrypted at rest and never returned.
    """

    enabled: bool
    base_url: str = Field(min_length=1, max_length=255)
    model: str = Field(min_length=1, max_length=64)
    api_key: str | None = Field(default=None, max_length=2048)


class LLMConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    enabled: bool
    base_url: str
    model: str
    api_key_masked: str | None = None
    updated_at: datetime
