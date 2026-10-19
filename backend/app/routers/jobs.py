import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import ARRAY, String, bindparam, delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.auth import get_current_user
from app.broker import enqueue_parse_jd, enqueue_tailor
from app.config import settings
from app.database import get_db
from app.models.application import Application
from app.models.enums import ApplicationStatus, CVVariant
from app.models.job import Job
from app.models.source import Source
from app.models.user import User
from app.ratelimit import auth_key, limiter
from app.schemas.generated_cv import TailorRequest, TailorResponse
from app.schemas.jd import ParsedJDResponse
from app.schemas.job import (
    JobCleanupRequest,
    JobCleanupResponse,
    JobCreate,
    JobResponse,
    JobSummary,
    JobUpdate,
)
from app.services.llm_config import get_llm_config, llm_variant_wanted
from app.services.search import keyword_filters

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


async def get_owned_job(job_id: uuid.UUID, user: User, db: AsyncSession) -> Job:
    """Fetch a job owned by the current user or raise 404."""
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == user.id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


async def validate_source(source_id: uuid.UUID | None, user: User, db: AsyncSession) -> None:
    """Ensure an optional source belongs to the current user."""
    if source_id is None:
        return
    result = await db.execute(
        select(Source.id).where(Source.id == source_id, Source.user_id == user.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")


@router.get("", response_model=list[JobSummary])
@limiter.limit(settings.rate_limit_api, key_func=auth_key)
async def list_jobs(
    request: Request,
    q: str | None = None,
    company: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    tags: str | None = None,
    source_id: uuid.UUID | None = None,
    created_after: datetime | None = None,
    include_hidden: bool = False,
    hide_applied: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search and filter jobs using PostgreSQL full-text search."""
    has_keyword = bool(q and q.strip())
    tsquery = None
    if has_keyword:
        predicates, tsquery = keyword_filters(q.strip())
        conditions = [Job.user_id == user.id, *predicates]
        if tsquery is not None:
            rank = func.ts_rank(Job.search_vector, tsquery)
            stmt = select(Job, rank.label("score")).where(*conditions)
        else:
            # The query was made only of special terms (``c++``/``go``), so
            # there is no tsquery to rank against.
            stmt = select(Job).where(*conditions)
    else:
        stmt = select(Job).where(Job.user_id == user.id)

    if not include_hidden:
        stmt = stmt.where(Job.hidden.is_(False))

    if hide_applied:
        stmt = stmt.where(
            ~select(Application.id)
            .where(
                Application.job_id == Job.id,
                Application.user_id == user.id,
                Application.status.in_(
                    (
                        ApplicationStatus.applied,
                        ApplicationStatus.interview,
                        ApplicationStatus.offer,
                        ApplicationStatus.rejected,
                    )
                ),
            )
            .exists()
        )

    if company:
        stmt = stmt.where(Job.company.ilike(f"%{company.strip()}%"))
    if date_from:
        stmt = stmt.where(Job.posted_date >= date_from)
    if date_to:
        stmt = stmt.where(Job.posted_date <= date_to)
    if tags:
        # Stored tags have mixed casing ("Rust", "Brazil"), while users type
        # lower-case filters.  Compare lowered values; JSONB `?|` is exact and
        # would silently miss those rows.
        tag_list = sorted({tag.strip().lower() for tag in tags.split(",") if tag.strip()})
        if tag_list:
            stmt = stmt.where(
                text(
                    "EXISTS (SELECT 1 FROM jsonb_array_elements_text(jobs.tags) AS tag "
                    "WHERE lower(tag) = ANY(:tag_values))"
                ).bindparams(
                    bindparam("tag_values", value=tag_list, type_=ARRAY(String))
                )
            )
    if source_id is not None:
        stmt = stmt.where(Job.source_id == source_id)
    if created_after is not None:
        # "Added" is Job.created_at (when the scraper stored the row), not the
        # employer's posted_date, which is often absent on scraped jobs.
        cutoff = created_after
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=UTC)
        stmt = stmt.where(Job.created_at >= cutoff)

    if tsquery is not None:
        stmt = stmt.order_by(
            func.ts_rank(Job.search_vector, tsquery).desc(), Job.created_at.desc()
        )
    else:
        stmt = stmt.order_by(Job.created_at.desc())

    result = await db.execute(stmt)
    if tsquery is not None:
        # select(Job, rank) returns tuples; rehydrate summaries with scores.
        return [
            JobSummary.model_validate(job).model_copy(update={"score": round(float(score), 4)})
            for job, score in result.all()
        ]
    return result.scalars().all()


@router.post("/cleanup", response_model=JobCleanupResponse)
@limiter.limit(settings.rate_limit_api, key_func=auth_key)
async def cleanup_jobs(
    request: Request,
    payload: JobCleanupRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Bulk-delete jobs older than N days and/or belonging to one source (ADR 023).

    ``dry_run`` (the default) only counts, so the client can show what a real run
    would remove before committing to it. Jobs that are already in the pipeline
    are spared unless ``include_with_applications`` is set, because deleting a job
    cascades its application away (``applications.job_id`` is ON DELETE CASCADE).
    """
    if payload.older_than_days is None and payload.source_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide older_than_days and/or source_id to select jobs",
        )
    # The source must belong to the caller; this also blocks an arbitrary UUID.
    await validate_source(payload.source_id, user, db)

    criteria = [Job.user_id == user.id]
    if payload.older_than_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=payload.older_than_days)
        criteria.append(Job.created_at < cutoff)
    if payload.source_id is not None:
        criteria.append(Job.source_id == payload.source_id)

    in_pipeline = (
        select(Application.id)
        .where(Application.job_id == Job.id, Application.user_id == user.id)
        .exists()
    )

    matched = await db.scalar(select(func.count(Job.id)).where(*criteria)) or 0
    protected = 0
    if not payload.include_with_applications:
        protected = await db.scalar(select(func.count(Job.id)).where(*criteria, in_pipeline)) or 0

    if payload.dry_run:
        return JobCleanupResponse(
            matched=matched, deleted=0, protected=protected, dry_run=True
        )

    statement = delete(Job).where(*criteria)
    if not payload.include_with_applications:
        statement = statement.where(~in_pipeline)
    result = await db.execute(statement)
    deleted = result.rowcount or 0
    await db.commit()

    await log_audit(
        db,
        user_id=user.id,
        action="bulk_deleted",
        entity_type="job",
        changes={
            "older_than_days": payload.older_than_days,
            "source_id": str(payload.source_id) if payload.source_id else None,
            "include_with_applications": payload.include_with_applications,
            "matched": matched,
            "deleted": deleted,
            "protected": protected,
        },
    )
    await db.commit()
    return JobCleanupResponse(
        matched=matched, deleted=deleted, protected=protected, dry_run=False
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await validate_source(payload.source_id, user, db)
    job = Job(user_id=user.id, **payload.model_dump())
    db.add(job)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A job with this URL already exists for the source",
        ) from exc
    await db.refresh(job)
    return job


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await get_owned_job(job_id, user, db)


@router.put("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: uuid.UUID,
    payload: JobUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await get_owned_job(job_id, user, db)
    if payload.source_id is not None:
        await validate_source(payload.source_id, user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    await db.commit()
    await db.refresh(job)
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = await get_owned_job(job_id, user, db)
    await db.delete(job)
    await db.commit()


@router.post("/{job_id}/parse", status_code=status.HTTP_202_ACCEPTED)
async def parse_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Enqueue JD parsing for a job (extract skills, years, education)."""
    await get_owned_job(job_id, user, db)
    enqueue_parse_jd(str(job_id))
    return {"enqueued": True, "job_id": str(job_id)}


@router.post(
    "/{job_id}/tailor", status_code=status.HTTP_202_ACCEPTED, response_model=TailorResponse
)
async def tailor_for_job(
    job_id: uuid.UUID,
    payload: TailorRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Enqueue CV tailoring; ``cv_id=None`` uses the current master CV."""
    await get_owned_job(job_id, user, db)
    cv_id = str(payload.cv_id) if payload and payload.cv_id else None
    application_id = str(payload.application_id) if payload and payload.application_id else None
    # Advertise the artifacts the run will produce (``rule`` always, plus ``llm``
    # when the LLM is enabled with a key). The client polls until the expected set
    # lands, so it does not stop at the deterministic variant while the slow AI
    # rewrite is still being written. Same rule the worker uses (ADR 016).
    variants = [CVVariant.rule]
    if llm_variant_wanted(await get_llm_config(db)):
        variants.append(CVVariant.llm)
    enqueue_tailor(str(job_id), cv_id, application_id)
    return TailorResponse(
        enqueued=True,
        job_id=job_id,
        cv_id=cv_id,
        application_id=application_id,
        variants=variants,
    )


@router.get("/{job_id}/parsed", response_model=ParsedJDResponse | None)
async def get_parsed_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the parsed JD requirements for a job (null if not parsed yet)."""
    job = await get_owned_job(job_id, user, db)
    return job.parsed_jd
