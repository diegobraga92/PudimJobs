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
    CVExportCapabilities,
    CVStructure,
    MasterCVCreate,
    MasterCVResponse,
    MasterCVUpdate,
)
from app.services.ats_scorer import derive_keywords, score_ats
from app.services.cv_labels import (
    DEFAULT_LANGUAGE,
    EXPORT_LANGUAGES,
    is_export_language,
    labels_for,
)
from app.services.cv_parser import CVParsingError, parse_cv_file
from app.services.cv_tailor import TailoredCV
from app.services.cv_translator import translate_cv_structure
from app.services.docx_generator import generate_docx
from app.services.jd_parser import parse_jd
from app.services.llm_config import get_llm_config, llm_variant_wanted
from app.services.pdf_generator import DEFAULT_TEMPLATE, TEMPLATES, generate_pdf

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/cv", tags=["cv"])

_MAX_CV_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
_SUPPORTED_CV_EXTENSIONS = {".pdf", ".docx", ".odt"}

# Download formats offered by both export endpoints (ADR 017). Only the canonical
# PDF is persisted on the artifact; DOCX is rendered on demand from the same
# `structured_json`, so an editable copy can never go stale.
PDF_MEDIA_TYPE = "application/pdf"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXPORT_FORMATS: dict[str, str] = {"pdf": PDF_MEDIA_TYPE, "docx": DOCX_MEDIA_TYPE}


def _account_name(email: str) -> str:
    """Best-effort display name: title-cased email local part (no name field)."""
    local = email.split("@")[0] or ""
    return " ".join(part.capitalize() for part in local.split(".") if part)


def _validate_export_format(fmt: str) -> str:
    """Reject an unknown download format the same way an unknown template is."""
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown format {fmt!r}; use one of {sorted(EXPORT_FORMATS)}",
        )
    return fmt


def _validate_export_language(language: str) -> str:
    """Reject an unknown export language the same way an unknown template is."""
    if not is_export_language(language):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown language {language!r}; use one of {list(EXPORT_LANGUAGES)}",
        )
    return language


async def _localized_structure(
    structure: dict, *, language: str, db: AsyncSession
) -> dict:
    """Return ``structure`` ready to render in ``language`` (ADR 024).

    English is the stored language, so it is passed straight through. Any other
    language is translated on demand by the LLM; when the LLM is not usable the
    request fails with 409 rather than shipping a half-translated CV, and a failed
    translation is a 502 because the cause is upstream.
    """
    if language == DEFAULT_LANGUAGE:
        return structure
    config = await get_llm_config(db)
    if not llm_variant_wanted(config):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A CV can only be exported in {language} with the LLM enabled "
                "(Admin -> LLM, with an API key)"
            ),
        )
    translated = await translate_cv_structure(
        structure, target_language=language, config=config
    )
    if translated is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The CV could not be translated into {language}; try again in a moment",
        )
    return translated


def _render_export(
    tailored: TailoredCV,
    *,
    fmt: str,
    template: str,
    language: str,
    name: str,
    email: str,
) -> bytes:
    """Render one CV structure in the requested download format and language."""
    labels = labels_for(language)
    if fmt == "docx":
        # A single plain layout: the classic/ATS split is a PDF-styling concern.
        return generate_docx(tailored, name=name, email=email, labels=labels)
    return generate_pdf(tailored, name=name, email=email, template=template, labels=labels)


def _language_suffix(language: str) -> str:
    """``""`` for the default language, ``-pt-br`` otherwise (never clobber a file)."""
    return "" if language == DEFAULT_LANGUAGE else f"-{language.lower()}"


def _export_filename(fmt: str, template: str, language: str = DEFAULT_LANGUAGE) -> str:
    suffix = _language_suffix(language)
    if fmt == "docx":
        return f"cv{suffix}.docx"
    return ("cv-ats" if template == "ats" else "cv") + f"{suffix}.pdf"


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


@router.get("/capabilities", response_model=CVExportCapabilities)
async def get_capabilities(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """What the export endpoints can produce right now (ADR 024).

    The client has no other way to know whether the LLM is on: the only settings
    endpoint is admin-only, and offering a language the server will refuse with
    409 is a worse experience than not offering it.
    """
    config = await get_llm_config(db)
    return CVExportCapabilities(
        llm_enabled=llm_variant_wanted(config),
        export_languages=list(EXPORT_LANGUAGES),
        default_language=DEFAULT_LANGUAGE,
    )


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
        TailoredCV.from_structure(structure), name=_account_name(user.email), email=user.email
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
    format: str = "pdf",
    language: str = DEFAULT_LANGUAGE,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Download a generated tailored CV as PDF (default) or DOCX, in `language`.

    The stored PDF is served as bytes; DOCX is rendered on demand from the
    artifact's own ``structured_json``, so the editable copy always reflects the
    latest edit without a second stored binary (ADR 017). The path keeps its
    ``/pdf`` name for the clients that already call it — ``format`` is additive.

    A non-default ``language`` is translated on demand from that same structure
    and always rendered fresh, since the stored PDF is English (ADR 024).
    """
    _validate_export_format(format)
    _validate_export_language(language)
    result = await db.execute(
        select(GeneratedCV).where(GeneratedCV.id == generated_id, GeneratedCV.user_id == user.id)
    )
    generated = result.scalar_one_or_none()
    if generated is None:
        raise HTTPException(status_code=404, detail="Generated CV not found")

    if format == "pdf" and language == DEFAULT_LANGUAGE:
        content = generated.pdf
    else:
        if not generated.structured_json:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "This tailored CV has no stored structure to export as "
                    f"{format.upper()}"
                ),
            )
        structure = await _localized_structure(generated.structured_json, language=language, db=db)
        tailored = TailoredCV.from_structure(structure)
        labels = labels_for(language)
        if format == "docx":
            content = generate_docx(
                tailored, name=_account_name(user.email), email=user.email, labels=labels
            )
        else:
            content = generate_pdf(
                tailored, name=_account_name(user.email), email=user.email, labels=labels
            )

    filename = f"tailored-cv-{generated.id}{_language_suffix(language)}.{format}"
    return Response(
        content=content,
        media_type=EXPORT_FORMATS[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
async def export_cv(
    request: Request,
    payload: CVStructure,
    template: str = DEFAULT_TEMPLATE,
    format: str = "pdf",
    language: str = DEFAULT_LANGUAGE,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Render an (optionally edited) CV structure to a downloadable PDF or DOCX.

    The path keeps its ``/pdf`` name for the clients that already call it; the
    ``format`` (``pdf``, the default, or ``docx``) and ``language`` (``en``, the
    default, or ``pt-BR``, translated on demand — ADR 024) query parameters are
    additive.
    """
    if template not in TEMPLATES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown template {template!r}; use one of {sorted(TEMPLATES)}",
        )
    _validate_export_format(format)
    _validate_export_language(language)
    structure = await _localized_structure(payload.model_dump(), language=language, db=db)
    # `from_structure` rather than copying fields one by one: the hand-rolled
    # version dropped the LLM variant's labelled `skill_groups`, so an export
    # disagreed with the stored artifact it was made from.
    content = _render_export(
        TailoredCV.from_structure(structure),
        fmt=format,
        template=template,
        language=language,
        name=_account_name(user.email),
        email=user.email,
    )
    return Response(
        content=content,
        media_type=EXPORT_FORMATS[format],
        headers={
            "Content-Disposition": (
                f'attachment; filename="{_export_filename(format, template, language)}"'
            )
        },
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
