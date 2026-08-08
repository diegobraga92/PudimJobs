import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.auth import get_current_user
from app.database import get_db
from app.models.generated_cv import GeneratedCV
from app.models.job import Job
from app.models.master_cv import MasterCV
from app.models.user import User
from app.schemas.generated_cv import GeneratedCVResponse
from app.schemas.master_cv import MasterCVCreate, MasterCVResponse, MasterCVUpdate

router = APIRouter(prefix="/api/cv", tags=["cv"])


async def get_owned_cv(cv_id: uuid.UUID, user: User, db: AsyncSession) -> MasterCV:
    """Fetch a CV version owned by the current user or raise 404."""
    result = await db.execute(
        select(MasterCV).where(MasterCV.id == cv_id, MasterCV.user_id == user.id)
    )
    cv = result.scalar_one_or_none()
    if cv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CV version not found")
    return cv


@router.get("", response_model=list[MasterCVResponse])
async def list_versions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MasterCV)
        .where(MasterCV.user_id == user.id)
        .order_by(MasterCV.version.desc())
    )
    return result.scalars().all()


@router.get("/current", response_model=MasterCVResponse)
async def get_current(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_current.is_(True))
    )
    cv = result.scalar_one_or_none()
    if cv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No CV version exists yet"
        )
    return cv


@router.post("", response_model=MasterCVResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    payload: MasterCVCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new CV version and promote it to current."""
    result = await db.execute(
        select(func.max(MasterCV.version)).where(MasterCV.user_id == user.id)
    )
    next_version = (result.scalar() or 0) + 1

    await db.execute(
        update(MasterCV).where(MasterCV.user_id == user.id).values(is_current=False)
    )
    cv = MasterCV(
        user_id=user.id,
        version=next_version,
        is_current=True,
        label=payload.label or f"CV v{next_version}",
        structured_json=payload.structured_json.model_dump(),
    )
    db.add(cv)
    await db.commit()
    await db.refresh(cv)

    await log_audit(
        db,
        user_id=user.id,
        action="created",
        entity_type="master_cv",
        entity_id=cv.id,
        changes={"version": cv.version},
    )
    await db.commit()
    return cv


@router.get("/generated", response_model=list[GeneratedCVResponse])
async def list_generated(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List generated (tailored) CVs with their target job info."""
    result = await db.execute(
        select(GeneratedCV, Job)
        .join(Job, GeneratedCV.job_id == Job.id)
        .where(GeneratedCV.user_id == user.id)
        .order_by(GeneratedCV.created_at.desc())
    )
    rows = result.all()
    return [
        GeneratedCVResponse(
            id=generated.id,
            master_cv_id=generated.master_cv_id,
            job_id=generated.job_id,
            job_title=job.title if job else None,
            job_company=job.company if job else None,
            created_at=generated.created_at,
        )
        for generated, job in rows
    ]


@router.get("/generated/{generated_id}/pdf")
async def get_generated_pdf(
    generated_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Download a generated tailored CV as PDF."""
    result = await db.execute(
        select(GeneratedCV).where(
            GeneratedCV.id == generated_id, GeneratedCV.user_id == user.id
        )
    )
    generated = result.scalar_one_or_none()
    if generated is None:
        raise HTTPException(status_code=404, detail="Generated CV not found")
    return Response(
        content=generated.pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="tailored-cv-{generated.id}.pdf"'
        },
    )


@router.put("/{cv_id}", response_model=MasterCVResponse)
async def update_version(
    cv_id: uuid.UUID,
    payload: MasterCVUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cv = await get_owned_cv(cv_id, user, db)
    changes = {}
    for field, value in payload.model_dump(exclude_unset=True).items():
        current = getattr(cv, field)
        new_value = (
            value.model_dump() if field == "structured_json" and value is not None else value
        )
        if new_value != current:
            changes[field] = new_value
            setattr(cv, field, new_value)

    await db.commit()
    await db.refresh(cv)

    if changes:
        await log_audit(
            db,
            user_id=user.id,
            action="updated",
            entity_type="master_cv",
            entity_id=cv.id,
            changes=changes,
        )
        await db.commit()
    return cv
