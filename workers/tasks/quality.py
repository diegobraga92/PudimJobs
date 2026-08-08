"""Data quality Celery task.

Triggered by ``job.new`` events (dispatched from the event consumer). Runs
company/title/skill normalization, completeness scoring, and fuzzy duplicate
detection, then stores a ``scrape_quality`` row per job.
"""

import asyncio
import uuid

import structlog
from app.database import async_session_factory
from app.models import Job, ScrapeQuality
from app.services.normalization import (
    normalize_company,
    normalize_skills,
    normalize_title,
)
from app.services.quality import collect_issues, completeness_score, is_duplicate_of
from sqlalchemy import select

from workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _assess_quality(job_id: str) -> dict:
    async with async_session_factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            raise ValueError(f"Job {job_id} not found")

        # Duplicate detection against the user's other jobs (cross-source).
        others = (
            await session.execute(
                select(Job)
                .where(Job.user_id == job.user_id, Job.id != job.id)
                .order_by(Job.created_at.desc())
                .limit(500)
            )
        ).scalars().all()
        canonical = is_duplicate_of(job, others)

        original_tags = list(job.tags)
        normalized_company = normalize_company(job.company)
        normalized_title = normalize_title(job.title)
        normalized_skills = normalize_skills(original_tags)
        changed_skills = set(original_tags) != set(normalized_skills)
        # Apply skill normalization in place (e.g. "react.js" -> "react").
        job.tags = normalized_skills
        await session.flush()

        issues = collect_issues(
            job, is_duplicate=canonical is not None, canonical_id=str(canonical.id) if canonical else None
        )
        if changed_skills:
            issues.append("normalized skill tags")
        score = completeness_score(job)

        existing = await session.execute(
            select(ScrapeQuality).where(ScrapeQuality.job_id == job.id)
        )
        quality = existing.scalar_one_or_none()
        if quality is None:
            quality = ScrapeQuality(job_id=job.id)
            session.add(quality)

        quality.completeness_score = score
        quality.normalized_company = normalized_company
        quality.normalized_title = normalized_title
        quality.is_duplicate = canonical is not None
        quality.canonical_job_id = canonical.id if canonical else None
        quality.issues = issues
        await session.commit()

        logger.info(
            "quality_assessed",
            job_id=job_id,
            score=score,
            duplicate=canonical is not None,
            issues=len(issues),
        )
        return {
            "job_id": job_id,
            "completeness_score": score,
            "is_duplicate": canonical is not None,
            "normalized_company": normalized_company,
            "normalized_title": normalized_title,
            "issues": issues,
        }


@celery_app.task(
    name="workers.tasks.quality.assess_quality",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=30,
)
def assess_quality(job_id: str) -> dict:
    return asyncio.run(_assess_quality(job_id))
