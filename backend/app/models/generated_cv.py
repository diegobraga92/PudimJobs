import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GeneratedCV(Base):
    """A tailored CV rendered to PDF for a specific job."""

    __tablename__ = "generated_cvs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    master_cv_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("master_cv.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    pdf: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
