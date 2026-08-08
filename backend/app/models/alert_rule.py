import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AlertRule(Base):
    """A user's saved search — criteria that trigger notifications."""

    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    companies: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    remote_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    min_years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
