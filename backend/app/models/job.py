import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

_SEARCH_VECTOR_EXPR = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(company, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(description, '')), 'C')"
)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        # Idempotency for scraped jobs: a URL is unique per source.
        UniqueConstraint("source_id", "url", name="uq_jobs_source_url"),
        # Provider-native job ids dedupe re-postings that reuse a URL.
        UniqueConstraint("source_id", "external_id", name="uq_jobs_source_external_id"),
        # Full-text search index (PostgreSQL FTS, Phase 5).
        Index("ix_jobs_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    posted_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    parsed_jd: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Provider-native job id (RSS guid, ATS requisition id, JSON-LD identifier).
    # Raw HTML is intentionally NOT retained (copyright/ToS + storage).
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(_SEARCH_VECTOR_EXPR), nullable=True
    )
    # Soft-hide flag: lets users dismiss "not interesting" jobs (or jobs they
    # already applied to) so they stop cluttering the main listing.
    hidden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

