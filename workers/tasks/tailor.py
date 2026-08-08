"""CV tailoring Celery task.

Runs the rule-based tailoring engine over a job + master CV, optionally
rephrases bullets with an LLM, renders a PDF, and stores both a new CV version
and a ``GeneratedCV`` row.
"""

import asyncio
import uuid

import structlog
from app.database import async_session_factory
from app.models import GeneratedCV, Job, MasterCV, User
from app.services.cv_tailor import enhance_with_llm, tailor_cv
from app.services.jd_parser import parse_jd, parsed_jd_to_dict
from app.services.pdf_generator import generate_pdf
from sqlalchemy import func, select

from workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


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
                select(MasterCV).where(MasterCV.user_id == job.user_id, MasterCV.is_current.is_(True))
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

        # Rule-based tailoring (sync).
        tailored = tailor_cv(cv.structured_json, jd_skills, annotations=cv.annotations)

        # Optional LLM rephrasing of selected bullet points.
        if tailored.experience:
            for block in tailored.experience:
                if block.get("bullets"):
                    block["bullets"] = await enhance_with_llm(block["bullets"], jd_skills)

        # New CV version (not auto-promoted; the user reviews before saving).
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
        pdf_bytes = generate_pdf(
            tailored, name=user.email.split("@")[0] if user else "", email=user.email if user else ""
        )
        generated = GeneratedCV(
            user_id=cv.user_id,
            master_cv_id=new_cv.id,
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
