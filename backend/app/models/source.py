import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Uuid, func
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
    last_scraped: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health: Mapped[SourceHealth] = mapped_column(
        Enum(SourceHealth, native_enum=False, values_callable=enum_values),
        nullable=False,
        default=SourceHealth.healthy,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
