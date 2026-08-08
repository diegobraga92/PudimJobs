import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import ARRAY, String, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.broker import enqueue_parse_jd, enqueue_tailor
from app.config import settings
from app.database import get_db
from app.models.job import Job
from app.models.source import Source
from app.models.user import User
from app.ratelimit import auth_key, limiter
from app.schemas.generated_cv import TailorRequest
from app.schemas.jd import ParsedJDResponse
from app.schemas.job import JobCreate, JobResponse, JobSummary, JobUpdate

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


async def get_owned_job(job_id: uuid.UUID, user: User, db: AsyncSession) -> Job:
    """Fetch a job owned by the current user or raise 404."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search and filter jobs using PostgreSQL full-text search.

    The ``search_vector`` generated column weights title (A) > company (B) >
    description (C). Results are ordered by ``ts_rank`` when a keyword is
    given (with a per-result ``score``), otherwise by recency.
    """
    has_keyword = bool(q and q.strip())
    if has_keyword:
        query = func.plainto_tsquery("english", q.strip())
        rank = func.ts_rank(Job.search_vector, query)
        stmt = select(Job, rank.label("score")).where(
            Job.user_id == user.id, Job.search_vector.op("@@")(query)
        )
    else:
        stmt = select(Job).where(Job.user_id == user.id)

    if company:
        stmt = stmt.where(Job.company.ilike(f"%{company.strip()}%"))
    if date_from:
        stmt = stmt.where(Job.posted_date >= date_from)
    if date_to:
        stmt = stmt.where(Job.posted_date <= date_to)
    if tags:
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        if tag_list:
            # JSONB `?|` requires a text[] operand; cast the Python list explicitly.
            stmt = stmt.where(Job.tags.op("?|")(cast(tag_list, ARRAY(String))))

    if has_keyword:
        stmt = stmt.order_by(func.ts_rank(Job.search_vector, query).desc(), Job.created_at.desc())
    else:
        stmt = stmt.order_by(Job.created_at.desc())

    result = await db.execute(stmt)
    if has_keyword:
        # select(Job, rank) returns tuples; rehydrate summaries with scores.
        return [
            JobSummary.model_validate(job).model_copy(
                update={"score": round(float(score), 4)}
            )
            for job, score in result.all()
        ]
    return result.scalars().all()


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


@router.post("/{job_id}/tailor", status_code=status.HTTP_202_ACCEPTED)
async def tailor_for_job(
    job_id: uuid.UUID,
    payload: TailorRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Enqueue CV tailoring; ``cv_id=None`` uses the current master CV."""
    await get_owned_job(job_id, user, db)
    cv_id = str(payload.cv_id) if payload and payload.cv_id else None
    enqueue_tailor(str(job_id), cv_id)
    return {"enqueued": True, "job_id": str(job_id), "cv_id": cv_id}


@router.get("/{job_id}/parsed", response_model=ParsedJDResponse | None)
async def get_parsed_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the parsed JD requirements for a job (null if not parsed yet)."""
    job = await get_owned_job(job_id, user, db)
    return job.parsed_jd
