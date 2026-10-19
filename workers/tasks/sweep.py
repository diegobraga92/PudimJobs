"""The ``sweep_sources`` periodic task."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from app.config import settings
from app.database import async_session_factory
from app.models import Notification, ScrapeRun, Source
from app.models.enums import SourceType
from app.services.source_schedule import is_scrape_due
from app.services.source_watchlist import is_due, mark_reminded, was_reminded
from sqlalchemy import select

from workers.celery_app import celery_app
from workers.resilience import circuit_breaker_is_open, skip_backoff_active

logger = structlog.get_logger(__name__)


async def _remind_manual_sources(now: datetime) -> int:
    """Create one in-app reminder per due manual source (ADR 018).

    Reminders are de-duplicated per due period via ``config['reminded_at']``:
    a due source is announced once, not once per sweep, until the user marks it
    checked (which clears the flag and advances ``next_check_at``).

    Avoided sources are excluded outright (ADR 019): no reminder at all until
    the user restores them (which clears ``reminded_at`` for one fresh nudge).
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(Source).where(
                Source.type == SourceType.manual,
                Source.avoided_at.is_(None),
            )
        )
        reminded = 0
        for source in result.scalars().all():
            if not is_due(source, now) or was_reminded(source):
                continue
            session.add(
                Notification(
                    user_id=source.user_id,
                    channel="in_app",
                    title=f"Re-check source: {source.name}",
                    message=(
                        f"“{source.name}” is due for a manual check — open "
                        f"{source.url} and log any new postings."
                    ),
                    status="created",
                )
            )
            mark_reminded(source, now)
            reminded += 1
        if reminded:
            await session.commit()
    return reminded


async def _reap_stale_runs(now: datetime) -> int:
    """Fail runs left ``running`` by a worker that died or lost the broker.

    Without this, an orphaned run keeps the source looking busy forever and the
    UI shows a stale "running" badge. The threshold is above the hard task time
    limit, so a legitimate run can never be reaped.
    """
    cutoff = now - timedelta(minutes=settings.scrape_run_stale_minutes)
    async with async_session_factory() as session:
        result = await session.execute(
            select(ScrapeRun).where(
                ScrapeRun.status == "running",
                ScrapeRun.started_at < cutoff,
            )
        )
        stale = result.scalars().all()
        for run in stale:
            run.status = "failed"
            run.error = (
                "stale run: worker did not finish within "
                f"{settings.scrape_run_stale_minutes} minutes"
            )
            run.finished_at = now
        if stale:
            await session.commit()
    if stale:
        logger.warning(
            "sweep_reaped_stale_runs",
            count=len(stale),
            source_ids=[str(run.source_id) for run in stale],
        )
    return len(stale)


async def _active_source_ids(now: datetime) -> set[uuid.UUID]:
    """Sources with a live run; the sweep must not enqueue them again."""
    cutoff = now - timedelta(minutes=settings.scrape_run_stale_minutes)
    async with async_session_factory() as session:
        result = await session.execute(
            select(ScrapeRun.source_id).where(
                ScrapeRun.status == "running",
                ScrapeRun.started_at >= cutoff,
            )
        )
        return set(result.scalars().all())


async def _sweep() -> dict:
    now = datetime.now(timezone.utc)
    reaped = await _reap_stale_runs(now)
    active = await _active_source_ids(now)
    async with async_session_factory() as session:
        result = await session.execute(
            select(Source).where(
                # Manual sources are never scraped — they are hand-checked.
                Source.type != SourceType.manual,
                # Avoided sources are never fetched either (ADR 019): the user
                # flagged the board as one to stay away from.
                Source.avoided_at.is_(None),
            )
        )
        # Per-source cadence can differ, so due-ness is evaluated row by row.
        # The global freshness remains the floor (see source_schedule).
        sources = [source for source in result.scalars().all() if is_scrape_due(source, now)]

    scheduled = 0
    skipped = 0
    for source in sources:
        source_id = str(source.id)
        if source.id in active:
            # A previous run is still in flight; enqueueing again would only
            # duplicate the work and can push a task past consumer_timeout.
            logger.info("sweep_skip_in_flight", source_id=source_id)
            skipped += 1
            continue
        if skip_backoff_active(source_id):
            # Robots.txt / missing credentials will not fix themselves between
            # two 15-minute sweeps; retry once a day instead.
            logger.info("sweep_skip_backoff", source_id=source_id)
            skipped += 1
            continue
        if circuit_breaker_is_open(source_id):
            logger.info("sweep_skip_circuit_breaker", source_id=source_id)
            skipped += 1
            continue
        from workers.tasks.scrape import scrape_source

        scrape_source.delay(source_id)
        scheduled += 1

    reminded = await _remind_manual_sources(now)
    logger.info(
        "sweep_complete",
        due=len(sources),
        scheduled=scheduled,
        skipped=skipped,
        reaped=reaped,
        reminded=reminded,
    )
    return {
        "due": len(sources),
        "scheduled": scheduled,
        "skipped": skipped,
        "reminded": reminded,
    }


@celery_app.task(name="workers.tasks.sweep.sweep_sources")
def sweep_sources() -> dict:
    return asyncio.run(_sweep())

