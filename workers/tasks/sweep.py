"""The ``sweep_sources`` periodic task.

Runs on a schedule (Celery Beat) and enqueues a ``scrape_source`` task for
every source that is due for a scrape (never scraped, or stale by more than
``scrape_freshness_minutes``), skipping sources whose circuit breaker is open.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from app.config import settings
from app.database import async_session_factory
from app.models import Source
from sqlalchemy import or_, select

from workers.celery_app import celery_app
from workers.resilience import circuit_breaker_is_open

logger = structlog.get_logger(__name__)


async def _sweep() -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.scrape_freshness_minutes)
    async with async_session_factory() as session:
        result = await session.execute(
            select(Source).where(
                or_(Source.last_scraped.is_(None), Source.last_scraped < cutoff)
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

    logger.info("sweep_complete", due=len(sources), scheduled=scheduled)
    return {"due": len(sources), "scheduled": scheduled}


@celery_app.task(name="workers.tasks.sweep.sweep_sources")
def sweep_sources() -> dict:
    return asyncio.run(_sweep())
