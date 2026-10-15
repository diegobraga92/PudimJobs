"""The ``sweep_sources`` periodic task."""

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from app.config import settings
from app.database import async_session_factory
from app.models import Notification, Source
from app.models.enums import SourceType
from app.services.source_watchlist import is_due, mark_reminded, was_reminded
from sqlalchemy import or_, select

from workers.celery_app import celery_app
from workers.resilience import circuit_breaker_is_open

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


async def _sweep() -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=settings.scrape_freshness_minutes)
    async with async_session_factory() as session:
        result = await session.execute(
            select(Source).where(
                # Manual sources are never scraped — they are hand-checked.
                Source.type != SourceType.manual,
                # Avoided sources are never fetched either (ADR 019): the user
                # flagged the board as one to stay away from.
                Source.avoided_at.is_(None),
                or_(Source.last_scraped.is_(None), Source.last_scraped < cutoff),
            )
        )
        sources = result.scalars().all()

    scheduled = 0
    for source in sources:
        source_id = str(source.id)
        if circuit_breaker_is_open(source_id):
            logger.info("sweep_skip_circuit_breaker", source_id=source_id)
            continue
        from workers.tasks.scrape import scrape_source

        scrape_source.delay(source_id)
        scheduled += 1

    reminded = await _remind_manual_sources(now)
    logger.info(
        "sweep_complete",
        due=len(sources),
        scheduled=scheduled,
        reminded=reminded,
    )
    return {"due": len(sources), "scheduled": scheduled, "reminded": reminded}


@celery_app.task(name="workers.tasks.sweep.sweep_sources")
def sweep_sources() -> dict:
    return asyncio.run(_sweep())

