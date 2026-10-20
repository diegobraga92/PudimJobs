"""Read helpers for a source's health: its last run and the reason behind it.

Kept as a service (not router code) because both the owner-facing
``/api/sources`` router and the admin router report the same fields.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SourceHealth
from app.models.scrape_run import ScrapeRun
from app.models.source import Source


async def latest_runs(
    db: AsyncSession, source_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ScrapeRun]:
    """Most recent run per source, in one query (``DISTINCT ON``).

    The sources list must not turn into N+1 queries: the health column needs the
    last attempt for every row.
    """
    if not source_ids:
        return {}
    result = await db.execute(
        select(ScrapeRun)
        .where(ScrapeRun.source_id.in_(source_ids))
        .order_by(
            ScrapeRun.source_id, ScrapeRun.started_at.desc(), ScrapeRun.id.desc()
        )
        .distinct(ScrapeRun.source_id)
    )
    return {run.source_id: run for run in result.scalars().all()}


async def latest_run(db: AsyncSession, source_id: uuid.UUID) -> ScrapeRun | None:
    """Most recent run for a single source."""
    result = await db.execute(
        select(ScrapeRun)
        .where(ScrapeRun.source_id == source_id)
        .order_by(ScrapeRun.started_at.desc(), ScrapeRun.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def health_reason(source: Source, last_run: ScrapeRun | None) -> str | None:
    """Why a source is not healthy, in the words recorded by its last run.

    ``skipped`` runs carry the explanation ("robots.txt disallows this source",
    "robots.txt unreachable …"), so a degraded badge can say *why* instead of
    leaving the user to guess.
    """
    if source.health == SourceHealth.healthy or last_run is None:
        return None
    return last_run.error
