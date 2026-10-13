"""Application pipeline + retrospective endpoints.

The kanban CRUD lives here; ``GET /api/applications/lessons`` exposes the
cross-application ``lessons_learned`` feed (ADR 014).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.auth import get_current_user
from app.database import get_db
from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.generated_cv import GeneratedCV
from app.models.job import Job
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationDetail,
    ApplicationResponse,
    ApplicationUpdate,
    LessonEntry,
)

router = APIRouter(prefix="/api/applications", tags=["applications"])


async def get_owned_application(
    application_id: uuid.UUID, user: User, db: AsyncSession
) -> Application:
    """Fetch an application owned by the current user or raise 404."""
    result = await db.execute(
        select(Application).where(Application.id == application_id, Application.user_id == user.id)
    )
    application = result.scalar_one_or_none()
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return application


async def _ensure_generated_cv_owned(
    generated_cv_id: uuid.UUID | None, user: User, db: AsyncSession
) -> None:
    """Reject linking an application to another user's tailored CV (ADR 016)."""
    if generated_cv_id is None:
        return
    result = await db.execute(
        select(GeneratedCV).where(
            GeneratedCV.id == generated_cv_id, GeneratedCV.user_id == user.id
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated CV not found")


async def to_response(application: Application, job: Job) -> ApplicationResponse:
    return ApplicationResponse(**_response_fields(application, job))


async def to_detail(application: Application, job: Job) -> ApplicationDetail:
    """Application payload plus the job description (application workspace)."""
    return ApplicationDetail(**_response_fields(application, job), job_description=job.description)


def _response_fields(application: Application, job: Job) -> dict:
    return {
        "id": application.id,
        "job_id": application.job_id,
        "status": application.status,
        "applied_date": application.applied_date,
        "notes": application.notes,
        "lessons_learned": application.lessons_learned,
        "generated_cv_id": application.generated_cv_id,
        "created_at": application.created_at,
        "updated_at": application.updated_at,
        "job_title": job.title,
        "job_company": job.company,
        "job_url": job.url,
    }


@router.get("", response_model=list[ApplicationResponse])
async def list_applications(
    status_filter: ApplicationStatus | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List applications, optionally filtered by pipeline status."""
    stmt = (
        select(Application, Job)
        .join(Job, Application.job_id == Job.id)
        .where(Application.user_id == user.id)
    )
    if status_filter:
        stmt = stmt.where(Application.status == status_filter)
    stmt = stmt.order_by(Application.created_at.desc())
    rows = (await db.execute(stmt)).all()
    return [await to_response(application, job) for application, job in rows]


@router.get("/lessons", response_model=list[LessonEntry])
async def list_lessons(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List retrospective notes ("lessons learned") across applications.

    Only applications that actually carry a non-empty ``lessons_learned`` value
    are returned, most recently updated first — this backs the "Lessons
    Learned" page.
    """
    stmt = (
        select(Application, Job)
        .join(Job, Application.job_id == Job.id)
        .where(
            Application.user_id == user.id,
            Application.lessons_learned.is_not(None),
            Application.lessons_learned != "",
        )
        .order_by(Application.updated_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        LessonEntry(
            application_id=application.id,
            job_title=job.title,
            job_company=job.company,
            status=application.status,
            applied_date=application.applied_date,
            lessons_learned=application.lessons_learned or "",
            updated_at=application.updated_at,
        )
        for application, job in rows
    ]


@router.get("/{application_id}", response_model=ApplicationDetail)
async def get_application(
    application_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch one application with its job description.

    Backs the per-application workspace (pipeline + jobs details + CV panel).
    Declared after ``/lessons`` so the static path is not shadowed.
    """
    application = await get_owned_application(application_id, user, db)
    result = await db.execute(select(Job).where(Job.id == application.job_id))
    job = result.scalar_one()
    return await to_detail(application, job)


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create an application for a job owned by the current user."""
    result = await db.execute(select(Job).where(Job.id == payload.job_id, Job.user_id == user.id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    await _ensure_generated_cv_owned(payload.generated_cv_id, user, db)

    application = Application(user_id=user.id, **payload.model_dump())
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return await to_response(application, job)


@router.put("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update an application (status, notes, dates) with audit logging."""
    application = await get_owned_application(application_id, user, db)
    result = await db.execute(select(Job).where(Job.id == application.job_id))
    job = result.scalar_one()

    updates = payload.model_dump(exclude_unset=True)
    await _ensure_generated_cv_owned(updates.get("generated_cv_id"), user, db)
    changes: dict = {}
    for field, value in updates.items():
        current = getattr(application, field)
        if value != current:
            changes[field] = {"before": str(current), "after": str(value)}
            setattr(application, field, value)

    await db.commit()
    await db.refresh(application)

    if changes:
        await log_audit(
            db,
            user_id=user.id,
            action="updated",
            entity_type="application",
            entity_id=application.id,
            changes=changes,
        )
        await db.commit()
    return await to_response(application, job)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    application_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    application = await get_owned_application(application_id, user, db)
    await db.delete(application)
    await db.commit()
