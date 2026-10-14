"""CV tailoring Celery task (ADR 016)."""

import asyncio
import uuid
from io import BytesIO

import structlog
from pypdf import PdfReader
from sqlalchemy import select

from app.database import async_session_factory
from app.models import Application, CVVariant, GeneratedCV, Job, MasterCV, User
from app.services.cv_tailor import (
    LLM_TARGET_PAGES,
    TailoredCV,
    generate_tailored_cv_with_llm,
    tailor_cv,
)
from app.services.jd_parser import parse_jd, parsed_jd_to_dict
from app.services.llm_config import (
    LlmRuntimeConfig,
    get_llm_config,
    llm_variant_skip_reason,
    llm_variant_wanted,
)
from app.services.pdf_generator import generate_pdf
from workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _pdf_pages(pdf_bytes: bytes) -> int | None:
    """Page count of a rendered CV, or ``None`` when the PDF cannot be read."""
    try:
        return len(PdfReader(BytesIO(pdf_bytes)).pages)
    except Exception:  # noqa: BLE001 - an unreadable PDF must not fail a tailor run
        logger.warning("cv_artifact_pages_unreadable")
        return None


def _pdf_name(user: User | None) -> str:
    """Best-effort display name: title-cased email local part (no name field)."""
    if user is None:
        return ""
    local = user.email.split("@")[0]
    return " ".join(part.capitalize() for part in local.split(".") if part)


async def _find_generated(
    session, cv: MasterCV, job: Job, variant: CVVariant
) -> GeneratedCV | None:
    """Return an existing artifact for this job + source CV version + variant."""
    result = await session.execute(
        select(GeneratedCV).where(
            GeneratedCV.user_id == cv.user_id,
            GeneratedCV.job_id == job.id,
            GeneratedCV.source_master_cv_id == cv.id,
            GeneratedCV.variant == variant,
        )
    )
    return result.scalar_one_or_none()


def _has_content(row: GeneratedCV) -> bool:
    """True when an artifact actually carries its own CV content."""
    return bool(row.structured_json)


async def _link_application(
    session, application_id: str | None, cv: MasterCV, job: Job, generated_cv_id: uuid.UUID
) -> None:
    """Point an application at the CV artifact it was sent with."""
    if not application_id:
        return
    application = await session.get(Application, uuid.UUID(application_id))
    if application is None or application.user_id != cv.user_id or application.job_id != job.id:
        logger.warning("cv_tailor_application_link_skipped", application_id=application_id)
        return
    application.generated_cv_id = generated_cv_id


async def _store_variant(
    session,
    *,
    cv: MasterCV,
    job: Job,
    user: User | None,
    variant: CVVariant,
    structure: dict,
    llm_self_score: int | None = None,
    existing: GeneratedCV | None = None,
) -> GeneratedCV:
    """Render and persist one tailored artifact."""
    tailored = TailoredCV.from_structure(structure)
    pdf_bytes = generate_pdf(tailored, name=_pdf_name(user), email=user.email if user else "")
    pages = _pdf_pages(pdf_bytes)
    generated = existing if existing is not None else GeneratedCV(
        user_id=cv.user_id,
        source_master_cv_id=cv.id,
        job_id=job.id,
        variant=variant,
    )
    generated.structured_json = structure
    generated.pdf = pdf_bytes
    # Unscored on purpose: scoring is an explicit user action (ADR 013), so a
    # tailor run does not spend an LLM/CPU budget the user never asked for.
    generated.ats_score = None
    # The AI's own estimate is the one number worth keeping from generation time;
    # the rest of the report is produced on demand.
    generated.ats_report = (
        {"llm_self_score": llm_self_score} if llm_self_score is not None else None
    )
    if existing is None:
        session.add(generated)
    else:
        logger.info(
            "cv_tailored_empty_artifact_repaired",
            generated_cv_id=str(generated.id),
            variant=variant.value,
        )
    await session.commit()
    await session.refresh(generated)
    logger.info(
        "cv_artifact_pages",
        generated_cv_id=str(generated.id),
        variant=variant.value,
        pages=pages,
    )
    if variant == CVVariant.llm and pages is not None and pages > LLM_TARGET_PAGES:
        # Reported, never corrected: the prompt asks the AI variant for at most
        # LLM_TARGET_PAGES pages, so a longer PDF means the guidance was not
        # followed. Trimming it here would silently delete content the model (or
        # the user, after an edit) chose on purpose — the count is surfaced and
        # both variants stay available to compare.
        logger.warning(
            "llm_rewrite_over_page_budget",
            generated_cv_id=str(generated.id),
            variant=variant.value,
            pages=pages,
            target_pages=LLM_TARGET_PAGES,
        )
    return generated


def _llm_variant_skip_reason(config: LlmRuntimeConfig) -> str:
    """Why the full-LLM variant will not be produced, or ``""`` when it will."""
    return llm_variant_skip_reason(config)


def _llm_variant_wanted(config: LlmRuntimeConfig) -> bool:
    """The full-LLM variant needs an enabled LLM config with a usable API key."""
    return llm_variant_wanted(config)


async def _run_tailor(job_id: str, cv_id: str | None, application_id: str | None = None) -> dict:
    job_uuid = uuid.UUID(job_id)
    async with async_session_factory() as session:
        job = await session.get(Job, job_uuid)
        if job is None:
            raise ValueError(f"Job {job_id} not found")

        if cv_id:
            cv = await session.get(MasterCV, uuid.UUID(cv_id))
        else:
            result = await session.execute(
                select(MasterCV).where(
                    MasterCV.user_id == job.user_id, MasterCV.is_current.is_(True)
                )
            )
            cv = result.scalar_one_or_none()
        if cv is None:
            raise ValueError(f"No master CV found for job {job_id}")

        user = await session.get(User, job.user_id)

        # Ensure the JD is parsed (parse on demand if the job has no result yet).
        if not job.parsed_jd:
            parsed = parse_jd(job.description)
            job.parsed_jd = parsed_jd_to_dict(parsed)
            await session.commit()
        jd_skills = job.parsed_jd.get("skills", []) or []
        jd_text = job.description or ""

        llm_config = await get_llm_config(session)

        # Which variants should exist after this run.
        wanted: list[CVVariant] = [CVVariant.rule]
        if _llm_variant_wanted(llm_config):
            wanted.append(CVVariant.llm)
        else:
            # Never skip silently: the user sees a single CV and needs to know
            # which of the two conditions is missing (ADR 016).
            logger.info(
                "cv_tailored_llm_variant_skipped",
                job_id=job_id,
                reason=_llm_variant_skip_reason(llm_config),
            )

        existing: dict[CVVariant, GeneratedCV] = {}
        # Content-less rows are kept aside: they must not satisfy the
        # idempotency shortcut, and the run repairs them in place instead.
        empty: dict[CVVariant, GeneratedCV] = {}
        for variant in wanted:
            found = await _find_generated(session, cv, job, variant)
            if found is None:
                continue
            if _has_content(found):
                existing[variant] = found
            else:
                empty[variant] = found
        if empty:
            logger.info(
                "cv_tailored_empty_artifact_found",
                job_id=job_id,
                variants=sorted(variant.value for variant in empty),
                generated_cv_ids=[str(row.id) for row in empty.values()],
            )

        # Idempotency: re-tailoring the same job against the same source CV
        # version reuses the artifacts instead of minting new ones.
        if len(existing) == len(wanted):
            rule = existing[CVVariant.rule]
            await _link_application(session, application_id, cv, job, rule.id)
            await session.commit()
            logger.info("cv_tailored_reused", job_id=job_id, generated_cv_id=str(rule.id))
            return {
                "generated_cv_id": str(rule.id),
                "variant": rule.variant.value,
                "generated_cv_ids": {
                    variant.value: str(row.id) for variant, row in existing.items()
                },
                "llm_generated_cv_id": (
                    str(existing[CVVariant.llm].id) if CVVariant.llm in existing else None
                ),
                "relevance": None,
                "matched_skills": [],
                "missing_skills": [],
                "used_fallback": False,
                "already_exists": True,
            }

        # Deterministic variant (always produced).
        tailored = tailor_cv(cv.structured_json, jd_skills, annotations=cv.annotations)
        products: dict[CVVariant, GeneratedCV] = dict(existing)
        if CVVariant.rule not in products:
            products[CVVariant.rule] = await _store_variant(
                session,
                cv=cv,
                job=job,
                user=user,
                variant=CVVariant.rule,
                structure=tailored.as_structure(),
                existing=empty.get(CVVariant.rule),
            )

        # Optional full-LLM variant, kept alongside the deterministic one. A
        # failure here degrades gracefully — the rule artifact still ships.
        if CVVariant.llm in wanted and CVVariant.llm not in products:
            rewritten = await generate_tailored_cv_with_llm(
                cv.structured_json,
                jd_text=jd_text,
                jd_title=job.title,
                jd_skills=jd_skills,
                config=llm_config,
            )
            if rewritten is not None:
                structure, self_score = rewritten
                products[CVVariant.llm] = await _store_variant(
                    session,
                    cv=cv,
                    job=job,
                    user=user,
                    variant=CVVariant.llm,
                    structure=structure,
                    llm_self_score=self_score,
                    existing=empty.get(CVVariant.llm),
                )

        # Auto-link the deterministic variant only; the LLM variant is linked when
        # the user explicitly picks it (ADR 016).
        rule = products[CVVariant.rule]
        await _link_application(session, application_id, cv, job, rule.id)
        await session.commit()

        logger.info(
            "cv_tailored",
            job_id=job_id,
            generated_cv_id=str(rule.id),
            variants=sorted(variant.value for variant in products),
            matched=len(tailored.matched_skills),
            relevance=tailored.relevance,
        )
        return {
            "generated_cv_id": str(rule.id),
            "variant": CVVariant.rule.value,
            "generated_cv_ids": {
                variant.value: str(row.id) for variant, row in products.items()
            },
            "llm_generated_cv_id": (
                str(products[CVVariant.llm].id) if CVVariant.llm in products else None
            ),
            "relevance": round(tailored.relevance, 3),
            "matched_skills": tailored.matched_skills,
            "missing_skills": tailored.missing_skills,
            "used_fallback": tailored.used_fallback,
            "already_exists": False,
        }


@celery_app.task(
    name="workers.tasks.tailor.tailor_cv_task",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=30,
)
def tailor_cv_task(job_id: str, cv_id: str | None = None, application_id: str | None = None) -> dict:
    return asyncio.run(_run_tailor(job_id, cv_id, application_id))
