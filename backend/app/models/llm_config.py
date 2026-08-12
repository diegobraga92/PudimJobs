"""Global LLM configuration (single-row table, admin-editable).

The row is upserted with a fixed id so there is always at most one config.
``cv_tailor.enhance_with_llm`` reads the runtime config through
``app.services.llm_config.get_llm_config`` (DB row with env-var fallback).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Fixed id for the single config row.
LLM_CONFIG_ROW_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class LLMConfig(Base):
    __tablename__ = "llm_config"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=LLM_CONFIG_ROW_ID
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str] = mapped_column(
        String(255), nullable=False, default="https://api.openai.com/v1"
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="gpt-4o-mini")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
