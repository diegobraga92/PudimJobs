"""CV tailoring Celery task.

Runs the rule-based tailoring engine over a job + master CV, optionally
rephrases bullets with an LLM, renders a PDF, and stores both a new CV version
and a ``GeneratedCV`` row.
"""

import asyncio
import uuid

import structlog
from sqlalchemy import func, select

from app.database import async_session_factory
from app.models import GeneratedCV, Job, MasterCV, User
from app.services.cv_tailor import enhance_with_llm, tailor_cv
from app.services.jd_parser import parse_jd, parsed_jd_to_dict
from app.services.llm_config import get_llm_config
from app.services.pdf_generator import generate_pdf
from workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _pdf_name(user: User | None) -> str:
    """Best-effort display name: title-cased email local part (no name field)."""
    if user is None:
        return ""
    local = user.email.split("@")[0]
    return " ".join(part.capitalize() for part in local.split(".") if part)


async def _find_generated(session, cv: MasterCV, job: Job) -> GeneratedCV | None:
    """Return an existing tailored artifact for this job + source CV version."""
    result = await session.execute(
        select(GeneratedCV).where(
            GeneratedCV.user_id == cv.user_id,
            GeneratedCV.job_id == job.id,
            GeneratedCV.source_master_cv_id == cv.id,
        )
    )
    return result.scalar_one_or_none()


async def _run_tailor(job_id: str, cv_id: str | None) -> dict:
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

        # Serialize version allocation per user so two concurrent tailoring
        # runs can't collide on the (user_id, version) unique constraint.
        await session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(str(cv.user_id), 0)))
        )

        # Idempotency: re-tailoring the same job against the same source CV
        # version reuses the existing artifact instead of minting a new one.
        existing = await _find_generated(session, cv, job)
        if existing is not None:
            await session.commit()  # releases the advisory lock
            logger.info(
                "cv_tailored_reused",
                job_id=job_id,
                generated_cv_id=str(existing.id),
            )
            return {
                "generated_cv_id": str(existing.id),
                "master_cv_id": str(existing.master_cv_id),
                "relevance": None,
                "matched_skills": [],
                "missing_skills": [],
                "already_exists": True,
            }

        # Rule-based tailoring (sync).
        tailored = tailor_cv(cv.structured_json, jd_skills, annotations=cv.annotations)

        # Optional LLM rephrasing of selected bullet points (DB config, env fallback).
        llm_config = await get_llm_config(session)
        if tailored.experience and llm_config.enabled and llm_config.api_key:
            for block in tailored.experience:
                if block.get("bullets"):
                    block["bullets"] = await enhance_with_llm(
                        block["bullets"], jd_skills, config=llm_config
                    )

        # New CV version (not auto-promoted; the user reviews before saving).
        # `next_version` is computed under the advisory lock acquired above.
        result = await session.execute(
            select(func.max(MasterCV.version)).where(MasterCV.user_id == cv.user_id)
        )
        next_version = (result.scalar() or 0) + 1
        new_cv = MasterCV(
            user_id=cv.user_id,
            label=f"Tailored for {job.title} at {job.company}",
            version=next_version,
            is_current=False,
            structured_json={
                "summary": tailored.summary,
                "experience": tailored.experience,
                "education": tailored.education,
                "skills": tailored.skills,
                "projects": tailored.projects,
            },
        )
        session.add(new_cv)
        await session.commit()
        await session.refresh(new_cv)

        # Render PDF and persist the generated artifact.
        pdf_bytes = generate_pdf(tailored, name=_pdf_name(user), email=user.email if user else "")
        generated = GeneratedCV(
            user_id=cv.user_id,
            master_cv_id=new_cv.id,
            source_master_cv_id=cv.id,
            job_id=job.id,
            pdf=pdf_bytes,
        )
        session.add(generated)
        await session.commit()
        await session.refresh(generated)

        logger.info(
            "cv_tailored",
            job_id=job_id,
            master_cv_id=str(new_cv.id),
            matched=len(tailored.matched_skills),
            relevance=tailored.relevance,
        )
        return {
            "generated_cv_id": str(generated.id),
            "master_cv_id": str(new_cv.id),
            "relevance": round(tailored.relevance, 3),
            "matched_skills": tailored.matched_skills,
            "missing_skills": tailored.missing_skills,
        }


@celery_app.task(
    name="workers.tasks.tailor.tailor_cv_task",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=30,
)
def tailor_cv_task(job_id: str, cv_id: str | None = None) -> dict:
    return asyncio.run(_run_tailor(job_id, cv_id))
