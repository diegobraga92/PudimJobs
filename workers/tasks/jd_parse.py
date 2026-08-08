"""JD parsing Celery task: parse a job description and store structured
requirements on the job record."""

import asyncio
import uuid

import structlog
from app.database import async_session_factory
from app.models import Job
from app.services.jd_parser import parse_jd, parsed_jd_to_dict

from workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _parse_job(job_id: str) -> dict:
    async with async_session_factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        parsed = parse_jd(job.description)
        job.parsed_jd = parsed_jd_to_dict(parsed)
        await session.commit()
        logger.info("jd_parsed", job_id=job_id, skills=len(parsed.skills))
        return job.parsed_jd


@celery_app.task(
    name="workers.tasks.jd_parse.parse_jd_task",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=30,
)
def parse_jd_task(job_id: str) -> dict:
    return asyncio.run(_parse_job(job_id))
