"""Interview-preparation checklist endpoints (ADR 014)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.auth import get_current_user
from app.database import get_db
from app.models.application import Application
from app.models.enums import PrepStatus
from app.models.job import Job
from app.models.prep_task import PrepTask
from app.models.user import User
from app.schemas.prep_task import (
    PrepTaskCreate,
    PrepTaskResponse,
    PrepTaskUpdate,
)

router = APIRouter(prefix="/api/prep-tasks", tags=["prep-tasks"])


async def get_owned_task(task_id: uuid.UUID, user: User, db: AsyncSession) -> PrepTask:
    """Fetch a prep task owned by the current user or raise 404."""
    result = await db.execute(
        select(PrepTask).where(PrepTask.id == task_id, PrepTask.user_id == user.id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prep task not found")
    return task


async def _validate_links(
    payload: PrepTaskCreate | PrepTaskUpdate, user: User, db: AsyncSession
) -> None:
    """Ensure any referenced job/application belongs to the current user."""
    if payload.job_id is not None:
        job = await db.get(Job, payload.job_id)
        if job is None or job.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if payload.application_id is not None:
        application = await db.get(Application, payload.application_id)
        if application is None or application.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
            )


def to_response(task: PrepTask, job: Job | None) -> PrepTaskResponse:
    return PrepTaskResponse(
        id=task.id,
        title=task.title,
        category=task.category,
        status=task.status,
        due_date=task.due_date,
        notes=task.notes,
        job_id=task.job_id,
        application_id=task.application_id,
        job_title=job.title if job else None,
        job_company=job.company if job else None,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("", response_model=list[PrepTaskResponse])
async def list_prep_tasks(
    status_filter: PrepStatus | None = None,
    job_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List prep tasks, optionally filtered by status and/or job."""
    stmt = (
        select(PrepTask, Job)
        .outerjoin(Job, PrepTask.job_id == Job.id)
        .where(PrepTask.user_id == user.id)
    )
    if status_filter is not None:
        stmt = stmt.where(PrepTask.status == status_filter)
    if job_id is not None:
        stmt = stmt.where(PrepTask.job_id == job_id)

    status_rank = case(
        (PrepTask.status == PrepStatus.pending, 0),
        (PrepTask.status == PrepStatus.in_progress, 1),
        else_=2,
    )
    stmt = stmt.order_by(
        status_rank,
        PrepTask.due_date.is_(None),
        PrepTask.due_date.asc(),
        PrepTask.created_at.desc(),
    )
    rows = (await db.execute(stmt)).all()
    return [to_response(task, job) for task, job in rows]


@router.post("", response_model=PrepTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_prep_task(
    payload: PrepTaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a prep task for the current user."""
    await _validate_links(payload, user, db)
    task = PrepTask(user_id=user.id, **payload.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    job = await db.get(Job, task.job_id) if task.job_id else None
    return to_response(task, job)


@router.get("/{task_id}", response_model=PrepTaskResponse)
async def get_prep_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await get_owned_task(task_id, user, db)
    job = await db.get(Job, task.job_id) if task.job_id else None
    return to_response(task, job)


@router.put("/{task_id}", response_model=PrepTaskResponse)
async def update_prep_task(
    task_id: uuid.UUID,
    payload: PrepTaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a prep task (title, status, category, due date, notes, links)."""
    task = await get_owned_task(task_id, user, db)
    await _validate_links(payload, user, db)

    changes: dict = {}
    for field, value in payload.model_dump(exclude_unset=True).items():
        current = getattr(task, field)
        if value != current:
            changes[field] = {"before": str(current), "after": str(value)}
            setattr(task, field, value)

    await db.commit()
    await db.refresh(task)
    job = await db.get(Job, task.job_id) if task.job_id else None

    if changes:
        await log_audit(
            db,
            user_id=user.id,
            action="updated",
            entity_type="prep_task",
            entity_id=task.id,
            changes=changes,
        )
        await db.commit()
    return to_response(task, job)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prep_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await get_owned_task(task_id, user, db)
    await db.delete(task)
    await log_audit(
        db,
        user_id=user.id,
        action="deleted",
        entity_type="prep_task",
        entity_id=task_id,
    )
    await db.commit()
