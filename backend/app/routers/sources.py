import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.job import Job
from app.models.source import Source
from app.models.user import User
from app.schemas.source import SourceCreate, SourceResponse, SourceUpdate

router = APIRouter(prefix="/api/sources", tags=["sources"])


async def get_owned_source(source_id: uuid.UUID, user: User, db: AsyncSession) -> Source:
    """Fetch a source owned by the current user or raise 404."""
    result = await db.execute(
        select(Source).where(Source.id == source_id, Source.user_id == user.id)
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


async def _job_counts(db: AsyncSession, user: User) -> dict[uuid.UUID, int]:
    """Map source_id → number of jobs scraped by the current user."""
    result = await db.execute(
        select(Job.source_id, func.count(Job.id))
        .where(Job.user_id == user.id, Job.source_id.is_not(None))
        .group_by(Job.source_id)
    )
    return {source_id: count for source_id, count in result.all()}


def _attach_counts(
    sources: list[Source], counts: dict[uuid.UUID, int]
) -> list[SourceResponse]:
    return [
        SourceResponse.model_validate(source).model_copy(
            update={"jobs_count": counts.get(source.id, 0)}
        )
        for source in sources
    ]


@router.get("", response_model=list[SourceResponse])
async def list_sources(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Source).where(Source.user_id == user.id).order_by(Source.created_at.desc())
    )
    sources = result.scalars().all()
    counts = await _job_counts(db, user)
    return _attach_counts(list(sources), counts)


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    source = Source(user_id=user.id, **payload.model_dump())
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await get_owned_source(source_id, user, db)


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: uuid.UUID,
    payload: SourceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    source = await get_owned_source(source_id, user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    await db.commit()
    await db.refresh(source)
    return source


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    source = await get_owned_source(source_id, user, db)
    await db.delete(source)
    await db.commit()
