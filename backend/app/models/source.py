import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import SourceHealth, SourceType, enum_values


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, native_enum=False, values_callable=enum_values), nullable=False
    )
    # Adapter-specific settings (e.g. aggregator selectors/pagination).
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rate_limit_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # Scraping ethics: honour the target's robots.txt `Disallow` rules before
    # fetching. Off by default only if the operator explicitly opts out.
    respect_robots_txt: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_scraped: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health: Mapped[SourceHealth] = mapped_column(
        Enum(SourceHealth, native_enum=False, values_callable=enum_values),
        nullable=False,
        default=SourceHealth.healthy,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
