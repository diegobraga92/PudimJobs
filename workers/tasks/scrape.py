"""The ``scrape_source`` Celery task: full scraping pipeline for one source.

Pipeline: circuit-breaker check → rate limit → fetch → parse → normalize →
dedup insert → emit ``job.new`` events → update source health. Failures are
recorded in ``scrape_runs`` (the reprocessing/DLQ record) and trigger the
Redis-backed circuit breaker.
"""

import asyncio
import uuid
from datetime import datetime, timezone

import structlog
from app.database import async_session_factory
from app.models import Job, ScrapeRun, Source
from app.models.enums import SourceHealth
from celery import Task
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from api.events.producer import publish_job_new
from api.events.schemas import JobNewEvent
from scrapers.registry import get_scraper
from workers.celery_app import celery_app
from workers.resilience import (
    CircuitBreakerOpenError,
    circuit_breaker_is_open,
    circuit_breaker_record_failure,
    circuit_breaker_reset,
    rate_limit_mark,
    rate_limit_wait,
)

logger = structlog.get_logger(__name__)


async def _existing_urls(session, source_id: uuid.UUID) -> set[str]:
    result = await session.execute(
        select(Job.url).where(Job.source_id == source_id, Job.url.is_not(None))
    )
    return {row[0] for row in result if row[0]}


async def _finalize_run(
    session, run: ScrapeRun, *, status: str, new_jobs: int, error: str | None
) -> None:
    run.status = status
    run.new_jobs = new_jobs
    run.error = error
    run.finished_at = datetime.now(timezone.utc)
    await session.commit()


async def _store_jobs(
    source: Source, normalized: list[dict], session
) -> tuple[int, int, list[Job]]:
    """Insert normalized jobs, skipping duplicates by (source, url)."""
    existing = await _existing_urls(session, source.id)
    new_count = 0
    skip_count = 0
    stored: list[Job] = []
    for data in normalized:
        url = data.get("url")
        if url and url in existing:
            skip_count += 1
            continue
        job = Job(
            user_id=source.user_id,
            source_id=source.id,
            title=data["title"],
            company=data["company"],
            description=data.get("description"),
            url=url,
            posted_date=data.get("posted_date"),
            tags=data.get("tags") or [],
        )
        session.add(job)
        if url:
            existing.add(url)
        stored.append(job)
        new_count += 1
    try:
        await session.commit()
    except IntegrityError:
        # Rare race with the DB constraint; treat the whole batch as skipped.
        await session.rollback()
        return 0, len(normalized), []
    return new_count, skip_count, stored

async def _publish_events(source: Source, stored: list[Job]) -> None:
    for job in stored:
        publish_job_new(
            JobNewEvent(
                job_id=job.id,
                source_id=source.id,
                title=job.title,
                company=job.company,
                url=job.url,
                posted_date=job.posted_date,
                tags=job.tags,
            )
        )


async def _run_scrape(source_id: str) -> dict:
    source_uuid = uuid.UUID(source_id)
    started = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        source = await session.get(Source, source_uuid)
        if source is None:
            raise ValueError(f"Source {source_id} not found")

        run = ScrapeRun(source_id=source_uuid, status="running", started_at=started)
        session.add(run)
        await session.commit()

        if circuit_breaker_is_open(source_id):
            await _finalize_run(
                session, run, status="skipped", new_jobs=0, error="circuit breaker open"
            )
            raise CircuitBreakerOpenError(f"Circuit breaker open for source {source_id}")

    try:
        scraper = get_scraper(source.type)

        wait = rate_limit_wait(source.url, source.rate_limit_seconds)
        if wait > 0:
            await asyncio.sleep(wait)
        rate_limit_mark(source.url, source.rate_limit_seconds)

        page = await scraper.fetch(source.url)
        raw_jobs = scraper.parse(page)
        normalized = scraper.normalize(raw_jobs)

        async with async_session_factory() as session:
            new_count, skip_count, stored = await _store_jobs(source, normalized, session)
            run_row = await session.get(ScrapeRun, run.id)
            await _finalize_run(
                session, run_row, status="success", new_jobs=new_count, error=None
            )

            source = await session.get(Source, source_uuid)
            source.last_scraped = datetime.now(timezone.utc)
            source.health = SourceHealth.healthy
            await session.commit()

        await _publish_events(source, stored)
        circuit_breaker_reset(source_id)

        logger.info("scrape_success", source_id=source_id, new=new_count, skipped=skip_count)
        return {"source_id": source_id, "new": new_count, "skipped": skip_count}
    except Exception as exc:
        circuit_breaker_record_failure(source_id)
        async with async_session_factory() as session:
            source_row = await session.get(Source, source_uuid)
            if source_row is not None:
                source_row.health = SourceHealth.failing
            run_row = await session.get(ScrapeRun, run.id)
            if run_row is not None:
                await _finalize_run(
                    session, run_row, status="failed", new_jobs=0, error=str(exc)[:1024]
                )
            else:
                await session.commit()
        logger.exception("scrape_failed", source_id=source_id)
        raise


@celery_app.task(
    bind=True,
    name="workers.tasks.scrape.scrape_source",
    autoretry_for=(Exception,),
    exclude_autoretry_for=(CircuitBreakerOpenError, ValueError),
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=600,
)
def scrape_source(self: Task, source_id: str) -> dict:
    """Celery entry point; wraps the async pipeline with ``asyncio.run``."""
    return asyncio.run(_run_scrape(source_id))

