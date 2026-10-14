import uuid
from pathlib import Path

import structlog
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
from app.schemas.ats import AtsScoreRequest, AtsScoreResponse
from app.schemas.generated_cv import GeneratedCVResponse, GeneratedCVUpdate
from app.schemas.master_cv import (
    CVStructure,
    MasterCVCreate,
    MasterCVResponse,
    MasterCVUpdate,
)
from app.services.ats_scorer import derive_keywords, score_ats
from app.services.cv_parser import CVParsingError, parse_cv_file
from app.services.cv_tailor import TailoredCV
from app.services.jd_parser import parse_jd
from app.services.llm_config import get_llm_config
from app.services.pdf_generator import TEMPLATES, generate_pdf

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/cv", tags=["cv"])

_MAX_CV_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
_SUPPORTED_CV_EXTENSIONS = {".pdf", ".docx", ".odt"}


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


def _generated_response(generated: GeneratedCV, job: Job | None) -> GeneratedCVResponse:
    """Serialise a tailored artifact with its (optional) target job (ADR 016)."""
    return GeneratedCVResponse(
        id=generated.id,
        job_id=generated.job_id,
        job_title=job.title if job else None,
        job_company=job.company if job else None,
        source_master_cv_id=generated.source_master_cv_id,
        variant=generated.variant,
        created_at=generated.created_at,
        updated_at=generated.updated_at,
        structured_json=generated.structured_json,
        ats_score=generated.ats_score,
        ats_report=generated.ats_report,
    )


async def get_owned_generated(
    generated_id: uuid.UUID, user: User, db: AsyncSession
) -> GeneratedCV:
    """Fetch a tailored CV owned by the current user or raise 404."""
    result = await db.execute(
        select(GeneratedCV).where(GeneratedCV.id == generated_id, GeneratedCV.user_id == user.id)
    )
    generated = result.scalar_one_or_none()
    if generated is None:
        raise HTTPException(status_code=404, detail="Generated CV not found")
    return generated


@router.get("", response_model=list[MasterCVResponse])
async def list_versions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MasterCV).where(MasterCV.user_id == user.id).order_by(MasterCV.version.desc())
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
    """Extract and structure an uploaded PDF/DOCX CV (never persisted)."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _SUPPORTED_CV_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type; upload a PDF, DOCX or ODT",
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
        return await parse_cv_file(file.filename or f"cv{suffix}", content, llm_config=llm_config)
    except CVParsingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("", response_model=MasterCVResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    payload: MasterCVCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new CV version and promote it to current."""
    result = await db.execute(select(func.max(MasterCV.version)).where(MasterCV.user_id == user.id))
    next_version = (result.scalar() or 0) + 1

    await db.execute(update(MasterCV).where(MasterCV.user_id == user.id).values(is_current=False))
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
    job_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List generated (tailored) CVs with their target job info."""
    stmt = (
        select(GeneratedCV, Job)
        .outerjoin(Job, GeneratedCV.job_id == Job.id)
        .where(GeneratedCV.user_id == user.id)
    )
    if job_id is not None:
        stmt = stmt.where(GeneratedCV.job_id == job_id)
    stmt = stmt.order_by(GeneratedCV.created_at.desc())
    rows = (await db.execute(stmt)).all()

    empty = [generated for generated, _ in rows if not generated.structured_json]
    if empty:
        logger.info(
            "cv_artifact_without_content_hidden",
            job_id=str(job_id) if job_id else None,
            generated_cv_ids=[str(generated.id) for generated in empty],
            variants=[generated.variant.value for generated in empty],
        )

    return [
        _generated_response(generated, job)
        for generated, job in rows
        if generated.structured_json
    ]


@router.get("/generated/{generated_id}", response_model=GeneratedCVResponse)
async def get_generated_cv(
    generated_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch one generated CV, including the structured content it was built from."""
    result = await db.execute(
        select(GeneratedCV, Job)
        .outerjoin(Job, GeneratedCV.job_id == Job.id)
        .where(GeneratedCV.id == generated_id, GeneratedCV.user_id == user.id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Generated CV not found")
    generated, job = row
    return _generated_response(generated, job)


@router.put("/generated/{generated_id}", response_model=GeneratedCVResponse)
async def update_generated_cv(
    generated_id: uuid.UUID,
    payload: GeneratedCVUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Edit a tailored CV in place."""
    generated = await get_owned_generated(generated_id, user, db)
    structure = payload.structured_json.model_dump()

    generated.structured_json = structure
    generated.pdf = generate_pdf(
        TailoredCV.from_structure(structure), name=_pdf_name(user.email), email=user.email
    )
    # The cached score tested the *old* content — never serve it for the new one.
    generated.ats_score = None
    generated.ats_report = None
    await db.commit()
    await db.refresh(generated)

    await log_audit(
        db,
        user_id=user.id,
        action="updated",
        entity_type="generated_cv",
        entity_id=generated.id,
        changes={"structured_json": "edited"},
    )
    await db.commit()

    job = await db.get(Job, generated.job_id) if generated.job_id else None
    return _generated_response(generated, job)


@router.get("/generated/{generated_id}/pdf")
async def get_generated_pdf(
    generated_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Download a generated tailored CV as PDF."""
    result = await db.execute(
        select(GeneratedCV).where(GeneratedCV.id == generated_id, GeneratedCV.user_id == user.id)
    )
    generated = result.scalar_one_or_none()
    if generated is None:
        raise HTTPException(status_code=404, detail="Generated CV not found")
    return Response(
        content=generated.pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="tailored-cv-{generated.id}.pdf"'},
    )


@router.delete("/generated/{generated_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_generated_cv(
    generated_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a generated (tailored) CV and its stored PDF."""
    result = await db.execute(
        select(GeneratedCV).where(GeneratedCV.id == generated_id, GeneratedCV.user_id == user.id)
    )
    generated = result.scalar_one_or_none()
    if generated is None:
        raise HTTPException(status_code=404, detail="Generated CV not found")
    await db.delete(generated)
    await db.commit()


@router.post("/pdf")
@limiter.limit(settings.rate_limit_api, key_func=auth_key)
async def export_cv_pdf(
    request: Request,
    payload: CVStructure,
    template: str = "classic",
    user: User = Depends(get_current_user),
):
    """Render an (optionally edited) CV structure to a downloadable PDF."""
    if template not in TEMPLATES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown template {template!r}; use one of {sorted(TEMPLATES)}",
        )
    tailored = TailoredCV(
        summary=payload.summary,
        experience=[item.model_dump() for item in payload.experience],
        education=[item.model_dump() for item in payload.education],
        skills=payload.skills,
        projects=[item.model_dump() for item in payload.projects],
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        location=payload.location,
        links=payload.links,
        certifications=payload.certifications,
        languages=payload.languages,
    )
    pdf = generate_pdf(
        tailored,
        name=_pdf_name(user.email),
        email=user.email,
        template=template,
    )
    filename = "cv-ats.pdf" if template == "ats" else "cv.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{cv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    cv_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a master CV version."""
    cv = await get_owned_cv(cv_id, user, db)
    was_current = cv.is_current
    deleted_version = cv.version

    await db.delete(cv)

    if was_current:
        result = await db.execute(
            select(MasterCV.id)
            .where(MasterCV.user_id == user.id)
            .order_by(MasterCV.version.desc())
            .limit(1)
        )
        next_current_id = result.scalar_one_or_none()
        if next_current_id is not None:
            await db.execute(
                update(MasterCV).where(MasterCV.id == next_current_id).values(is_current=True)
            )

    await log_audit(
        db,
        user_id=user.id,
        action="deleted",
        entity_type="master_cv",
        entity_id=cv_id,
        changes={"version": deleted_version},
    )
    await db.commit()


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


@router.post("/ats-score", response_model=AtsScoreResponse)
@limiter.limit(settings.rate_limit_api, key_func=auth_key)
async def score_cv_ats(
    request: Request,
    payload: AtsScoreRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Score an (optionally edited) CV structure against a job description."""
    jd_text = payload.job_description or ""
    jd_title = payload.job_title
    jd_skills: list[str] = []
    jd_keywords: list[str] = []

    if payload.job_id is not None:
        job = await db.get(Job, payload.job_id)
        if job is None or job.user_id != user.id:
            raise HTTPException(status_code=404, detail="Job not found")
        jd_text = jd_text or (job.description or "")
        jd_title = jd_title or job.title
        stored = job.parsed_jd or {}
        jd_skills = [str(s) for s in stored.get("skills") or []]
        jd_keywords = [str(k) for k in stored.get("keywords") or []]

    # No stored/parsed requirements: parse the description on the fly.
    if not jd_skills and jd_text:
        jd_skills = parse_jd(jd_text).skills
    if not jd_keywords and jd_text:
        jd_keywords = derive_keywords(jd_text)

    report = await score_ats(
        payload.cv.model_dump(),
        jd_skills=jd_skills,
        jd_keywords=jd_keywords,
        jd_text=jd_text,
        job_title=jd_title,
        llm_config=await get_llm_config(db),
    )

    if payload.generated_cv_id is not None:
        generated = await db.get(GeneratedCV, payload.generated_cv_id)
        if generated is not None and generated.user_id == user.id:
            # Re-scoring must not lose the LLM variant's own estimate (ADR 016).
            previous = (generated.ats_report or {}).get("llm_self_score")
            if previous is not None:
                report["llm_self_score"] = previous
            generated.ats_score = report["score"]
            generated.ats_report = report
            await log_audit(
                db,
                user_id=user.id,
                action="scored",
                entity_type="generated_cv",
                entity_id=generated.id,
                changes={"ats_score": report["score"]},
            )
            await db.commit()

    return AtsScoreResponse(**report)
