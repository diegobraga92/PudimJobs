import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.auth import get_current_user
from app.database import get_db
from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.job import Job
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
)

router = APIRouter(prefix="/api/applications", tags=["applications"])


async def get_owned_application(
    application_id: uuid.UUID, user: User, db: AsyncSession
) -> Application:
    """Fetch an application owned by the current user or raise 404."""
    result = await db.execute(
        select(Application).where(
            Application.id == application_id, Application.user_id == user.id
        )
    )
    application = result.scalar_one_or_none()
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )
    return application


async def to_response(application: Application, job: Job) -> ApplicationResponse:
    return ApplicationResponse(
        id=application.id,
        job_id=application.job_id,
        status=application.status,
        applied_date=application.applied_date,
        notes=application.notes,
        cv_version=application.cv_version,
        created_at=application.created_at,
        updated_at=application.updated_at,
        job_title=job.title,
        job_company=job.company,
        job_url=job.url,
    )


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


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create an application for a job owned by the current user."""
    result = await db.execute(
        select(Job).where(Job.id == payload.job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

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
