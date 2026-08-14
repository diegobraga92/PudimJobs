import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.generated_cv import GeneratedCV
from app.models.job import Job
from app.models.master_cv import MasterCV
from app.models.user import User
from app.ratelimit import auth_key, limiter
from app.schemas.generated_cv import GeneratedCVResponse
from app.schemas.master_cv import (
    CVStructure,
    MasterCVCreate,
    MasterCVResponse,
    MasterCVUpdate,
)
from app.services.cv_parser import CVParsingError, parse_cv_file
from app.services.cv_tailor import TailoredCV
from app.services.llm_config import get_llm_config
from app.services.pdf_generator import generate_pdf

router = APIRouter(prefix="/api/cv", tags=["cv"])

_MAX_CV_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
_SUPPORTED_CV_EXTENSIONS = {".pdf", ".docx"}


def _pdf_name(email: str) -> str:
    """Best-effort display name: title-cased email local part (no name field)."""
    local = email.split("@")[0] or ""
    return " ".join(part.capitalize() for part in local.split(".") if part)


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


@router.post("/parse", response_model=CVStructure)
@limiter.limit(settings.rate_limit_api, key_func=auth_key)
async def parse_uploaded_cv(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Extract and structure an uploaded PDF/DOCX CV (never persisted).

    Returns a CVStructure the frontend can pre-fill the editor with; the user
    reviews it and saves via ``POST /api/cv``. Structuring is rule-based by
    default and upgraded by the LLM when one is configured (ADR 011).
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _SUPPORTED_CV_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type; upload a PDF or DOCX",
        )
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty"
        )
    if len(content) > _MAX_CV_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (max 5 MB)",
        )

    try:
        llm_config = await get_llm_config(db)
        return await parse_cv_file(
            file.filename or f"cv{suffix}", content, llm_config=llm_config
        )
    except CVParsingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


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


@router.post("/pdf")
@limiter.limit(settings.rate_limit_api, key_func=auth_key)
async def export_cv_pdf(
    request: Request,
    payload: CVStructure,
    user: User = Depends(get_current_user),
):
    """Render an (optionally edited) CV structure to a downloadable PDF.

    Lets the user tweak a tailored CV in the editor and export the result
    without going through the tailoring worker again. Nothing is persisted.
    """
    tailored = TailoredCV(
        summary=payload.summary,
        experience=[item.model_dump() for item in payload.experience],
        education=[item.model_dump() for item in payload.education],
        skills=payload.skills,
        projects=[item.model_dump() for item in payload.projects],
    )
    pdf = generate_pdf(tailored, name=_pdf_name(user.email), email=user.email)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="cv.pdf"'},
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
