"""The ``scrape_source`` Celery task: full scraping pipeline for one source.

Pipeline: circuit-breaker check → rate limit → fetch → parse → normalize →
dedup insert → emit ``job.new`` events → update source health. Failures are
recorded in ``scrape_runs`` (the reprocessing/DLQ record) and trigger the
Redis-backed circuit breaker.
"""

import asyncio
import inspect
import time
import uuid
from datetime import UTC, datetime

import httpx
import structlog
from api.events.producer import publish_job_new
from api.events.schemas import JobNewEvent
from celery import Task
from scrapers.registry import get_scraper
from scrapers.utils import is_allowed_by_robots, redact_sensitive
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import async_session_factory
from app.models import Job, ScrapeRun, Source
from app.models.enums import SourceHealth
from app.models.source_auth import SourceAuth
from app.services.source_auth import build_fetch_auth
from workers.celery_app import celery_app
from workers.metrics import SCRAPE_DURATION, SCRAPES_TOTAL
from workers.resilience import (
    CircuitBreakerOpenError,
    circuit_breaker_is_open,
    circuit_breaker_record_failure,
    circuit_breaker_reset,
    rate_limit_mark,
    rate_limit_wait,
)

logger = structlog.get_logger(__name__)


class EmptyScrapeError(Exception):
    """Raised when a scrape completes but parses zero jobs.

    Usually signals a site format change or broken selectors; the circuit
    breaker trips after repeated occurrences (see postmortem 001). Sources that
    are legitimately empty can opt out with ``config['allow_empty'] = true``.
    """


async def _existing_keys(session, source_id: uuid.UUID) -> tuple[set[str], set[str]]:
    """Return the URLs and provider-native external ids already stored."""
    result = await session.execute(
        select(Job.url, Job.external_id).where(Job.source_id == source_id)
    )
    urls: set[str] = set()
    external_ids: set[str] = set()
    for url, external_id in result:
        if url:
            urls.add(url)
        if external_id:
            external_ids.add(external_id)
    return urls, external_ids


async def _finalize_run(
    session, run: ScrapeRun, *, status: str, new_jobs: int, error: str | None
) -> None:
    run.status = status
    run.new_jobs = new_jobs
    run.error = error
    run.finished_at = datetime.now(UTC)
    await session.commit()


def _robots_allowed(source: Source, url: str) -> bool:
    """Robots.txt gate: always allowed unless the source opts in to checks."""
    if not source.respect_robots_txt:
        return True
    return is_allowed_by_robots(url)


async def _skip_run(source_id: str, run: ScrapeRun, reason: str) -> dict:
    """Record the run as *skipped* (never trips the circuit breaker)."""
    async with async_session_factory() as session:
        run_row = await session.get(ScrapeRun, run.id)
        await _finalize_run(
            session, run_row, status="skipped", new_jobs=0, error=reason
        )
    logger.info("scrape_skipped", source_id=source_id, reason=reason)
    return {"source_id": source_id, "skipped": True, "reason": reason}


async def _discover(scraper, page) -> list[str]:
    """Extract detail URLs from a page, tolerating scrapers without the hook.

    The contract hook is async; some duck-typed scrapers (e.g. test doubles)
    omit it or implement it synchronously, so this also covers those cases.
    """
    discover = getattr(scraper, "discover_urls", None)
    if not callable(discover):
        return []
    result = discover(page)
    if inspect.isawaitable(result):
        result = await result
    return result or []


async def _store_jobs(
    source: Source, normalized: list[dict], session
) -> tuple[int, int, list[Job]]:
    """Insert normalized jobs, skipping duplicates by URL or external id."""
    existing_urls, existing_external_ids = await _existing_keys(session, source.id)
    new_count = 0
    skip_count = 0
    stored: list[Job] = []
    for data in normalized:
        url = data.get("url")
        external_id = data.get("external_id")
        if url and url in existing_urls:
            skip_count += 1
            continue
        if external_id and external_id in existing_external_ids:
            skip_count += 1
            continue
        job = Job(
            user_id=source.user_id,
            source_id=source.id,
            title=(data["title"] or "").strip()[:255],
            company=(data["company"] or "").strip()[:255],
            description=data.get("description"),
            url=url,
            posted_date=data.get("posted_date"),
            tags=data.get("tags") or [],
            external_id=external_id,
        )
        session.add(job)
        if url:
            existing_urls.add(url)
        if external_id:
            existing_external_ids.add(external_id)
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


def _config_int(source: Source, key: str, default: int) -> int:
    """Read an integer from ``source.config``, falling back on bad values."""
    raw = (source.config or {}).get(key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


async def _run_scrape(source_id: str) -> dict:
    source_uuid = uuid.UUID(source_id)
    started = datetime.now(UTC)

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
        # Optional per-source authentication (bearer token / API key).
        auth = None
        async with async_session_factory() as session:
            result = await session.execute(
                select(SourceAuth).where(SourceAuth.source_id == source_uuid)
            )
            record = result.scalar_one_or_none()
            auth = build_fetch_auth(record)

        scraper = get_scraper(source, api_key=auth.api_key if auth else None)

        # The first fetch may be a provider-built endpoint (discovery sources),
        # not the raw source URL.
        current_url = getattr(scraper, "first_fetch_url", lambda url: url)(source.url)

        # Scraping ethics: honour robots.txt before touching the target.
        if not _robots_allowed(source, current_url):
            return await _skip_run(source_id, run, "robots.txt disallows this source")

        wait = rate_limit_wait(current_url, source.rate_limit_seconds)
        if wait > 0:
            await asyncio.sleep(wait)
        rate_limit_mark(current_url, source.rate_limit_seconds)

        # Aggregators/ATS boards can paginate through several listing pages;
        # discovery sources additionally fetch each discovered detail URL.
        max_pages = _config_int(source, "max_pages", 1)
        max_results = _config_int(source, "max_results", 20)
        pages_fetched = 0
        detail_fetched = 0
        raw_jobs: list = []
        while True:
            page = await scraper.fetch(current_url, auth=auth)
            pages_fetched += 1

            discovered = await _discover(scraper, page)
            if discovered:
                for detail_url in discovered:
                    if detail_fetched >= max_results:
                        break
                    if not _robots_allowed(source, detail_url):
                        continue
                    wait = rate_limit_wait(detail_url, source.rate_limit_seconds)
                    if wait > 0:
                        await asyncio.sleep(wait)
                    rate_limit_mark(detail_url, source.rate_limit_seconds)
                    detail_page = await scraper.fetch(detail_url, auth=auth)
                    raw_jobs.extend(scraper.parse(detail_page))
                    detail_fetched += 1
            else:
                raw_jobs.extend(scraper.parse(page))

            if pages_fetched >= max_pages:
                break
            next_url = getattr(scraper, "next_page_url", lambda _page: None)(page)
            if not next_url or next_url == current_url:
                break
            current_url = next_url
            if not _robots_allowed(source, current_url):
                logger.info(
                    "scrape_stop_pagination",
                    source_id=source_id,
                    reason="robots.txt",
                    url=redact_sensitive(current_url),
                )
                break
            wait = rate_limit_wait(current_url, source.rate_limit_seconds)
            if wait > 0:
                await asyncio.sleep(wait)
            rate_limit_mark(current_url, source.rate_limit_seconds)

        normalized = scraper.normalize(raw_jobs)

        # Fail fast when a source yields no jobs at all: a site format change
        # or broken selectors usually manifests as an empty parse, and treating
        # it as "0 new jobs, success" hides the breakage (see postmortem 001).
        # Sources that are legitimately empty can opt out via config.
        allow_empty = bool((source.config or {}).get("allow_empty", False))
        if not normalized and not allow_empty:
            raise EmptyScrapeError(
                "parse produced 0 jobs; possible site format change "
                "(set config['allow_empty']=true to allow empty sources)"
            )

        async with async_session_factory() as session:
            new_count, skip_count, stored = await _store_jobs(source, normalized, session)
            run_row = await session.get(ScrapeRun, run.id)
            await _finalize_run(
                session, run_row, status="success", new_jobs=new_count, error=None
            )

            source = await session.get(Source, source_uuid)
            source.last_scraped = datetime.now(UTC)
            source.health = SourceHealth.healthy
            await session.commit()

        await _publish_events(source, stored)
        circuit_breaker_reset(source_id)

        logger.info("scrape_success", source_id=source_id, new=new_count, skipped=skip_count)
        return {"source_id": source_id, "new": new_count, "skipped": skip_count}
    except Exception as exc:
        circuit_breaker_record_failure(source_id)
        # A 401/403 from the target usually means the stored credentials are
        # stale or wrong — surface it as "degraded" instead of "failing".
        auth_failed = (
            isinstance(exc, httpx.HTTPStatusError)
            and exc.response.status_code in (401, 403)
        )
        error = (
            f"authentication failed (HTTP {exc.response.status_code})"
            if auth_failed
            else redact_sensitive(str(exc)[:1024])
        )
        async with async_session_factory() as session:
            source_row = await session.get(Source, source_uuid)
            if source_row is not None:
                source_row.health = SourceHealth.degraded if auth_failed else SourceHealth.failing
            run_row = await session.get(ScrapeRun, run.id)
            if run_row is not None:
                await _finalize_run(
                    session, run_row, status="failed", new_jobs=0, error=error
                )
            else:
                await session.commit()
        logger.exception("scrape_failed", source_id=source_id)
        raise


@celery_app.task(
    bind=True,
    name="workers.tasks.scrape.scrape_source",
    autoretry_for=(Exception,),
    exclude_autoretry_for=(CircuitBreakerOpenError, ValueError, EmptyScrapeError),
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=600,
)
def scrape_source(self: Task, source_id: str) -> dict:
    """Celery entry point; wraps the async pipeline with ``asyncio.run``."""
    started = time.monotonic()
    try:
        result = asyncio.run(_run_scrape(source_id))
        SCRAPES_TOTAL.labels(source_id=source_id, status="success").inc()
        return result
    except CircuitBreakerOpenError:
        SCRAPES_TOTAL.labels(source_id=source_id, status="skipped").inc()
        raise
    except Exception:
        SCRAPES_TOTAL.labels(source_id=source_id, status="failed").inc()
        raise
    finally:
        SCRAPE_DURATION.labels(source_id=source_id).observe(time.monotonic() - started)

