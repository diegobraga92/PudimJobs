import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import ARRAY, String, cast, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.job import Job
from app.models.source import Source
from app.models.user import User
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
async def list_jobs(
    q: str | None = None,
    company: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    tags: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search and filter jobs.

    Phase 1 uses ILIKE over title/company/description; PostgreSQL full-text
    search (tsvector + ranking) replaces this in Phase 5.
    """
    stmt = select(Job).where(Job.user_id == user.id)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Job.title.ilike(pattern),
                Job.company.ilike(pattern),
                Job.description.ilike(pattern),
            )
        )
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

    stmt = stmt.order_by(Job.created_at.desc())
    result = await db.execute(stmt)
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
