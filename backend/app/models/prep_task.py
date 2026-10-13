import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import PrepCategory, PrepStatus, enum_values


class PrepTask(Base):
    """An interview-preparation checklist item.

    Optionally scoped to a job and/or an application; a task with neither is a
    general preparation to-do.
    """

    __tablename__ = "prep_tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[PrepCategory] = mapped_column(
        Enum(PrepCategory, native_enum=False, values_callable=enum_values),
        nullable=False,
        default=PrepCategory.other,
    )
    status: Mapped[PrepStatus] = mapped_column(
        Enum(PrepStatus, native_enum=False, values_callable=enum_values),
        nullable=False,
        default=PrepStatus.pending,
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
