import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, LargeBinary, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import CVVariant, enum_values


class GeneratedCV(Base):
    """A tailored CV — a first-class artifact, not a master-CV version (ADR 016).

    Owns its ``structured_json`` (so it can be edited without touching the master
    CV) and a ``variant`` distinguishing the deterministic engine from the
    optional LLM rewrite. Idempotent per
    ``(user_id, job_id, source_master_cv_id, variant)``.
    """

    __tablename__ = "generated_cvs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # The source CV version this artifact was tailored from (idempotency key).
    source_master_cv_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("master_cv.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    variant: Mapped[CVVariant] = mapped_column(
        Enum(CVVariant, native_enum=False, values_callable=enum_values),
        nullable=False,
        default=CVVariant.rule,
    )
    # The tailored content itself; the master CV is never modified by a tailor run.
    structured_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pdf: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # ATS score (0-100) and the full breakdown report, cached so the UI can
    # display it without recomputing (see ADR 013).
    ats_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ats_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
