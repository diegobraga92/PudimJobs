import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from scrapers.registry import get_scraper
from scrapers.types import ScrapedPage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.auth import require_admin
from app.broker import enqueue_scrape
from app.database import get_db
from app.models import Job, ScrapeRun, Source
from app.models.user import User
from app.schemas.admin import (
    ReparseResponse,
    ReplayResponse,
    ScrapeRunResponse,
    SourceHealthResponse,
    StatsResponse,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/sources/health", response_model=list[SourceHealthResponse])
async def source_health(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(Source).order_by(Source.name))
    return result.scalars().all()


@router.get("/stats", response_model=StatsResponse)
async def stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    sources = await db.execute(select(func.count(Source.id)))
    jobs = await db.execute(select(func.count(Job.id)))
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    jobs_24h = await db.execute(
        select(func.count(Job.id)).where(Job.created_at >= cutoff)
    )
    failed = await db.execute(
        select(func.count(ScrapeRun.id)).where(ScrapeRun.status == "failed")
    )
    total_runs = await db.execute(select(func.count(ScrapeRun.id)))
    return StatsResponse(
        sources=sources.scalar() or 0,
        jobs=jobs.scalar() or 0,
        jobs_last_24h=jobs_24h.scalar() or 0,
        failed_runs=failed.scalar() or 0,
        total_runs=total_runs.scalar() or 0,
    )


@router.get("/dlq", response_model=list[ScrapeRunResponse])
async def list_dlq(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """List failed scrape runs (the reprocessing queue)."""
    result = await db.execute(
        select(ScrapeRun)
        .where(ScrapeRun.status == "failed")
        .order_by(ScrapeRun.started_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.post("/dlq/{run_id}/replay", response_model=ReplayResponse)
async def replay_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Re-enqueue the scrape for a failed run."""
    run = await db.get(ScrapeRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Scrape run not found")

    enqueue_scrape(str(run.source_id))
    await log_audit(
        db,
        user_id=admin.id,
        action="replay",
        entity_type="reprocessing",
        entity_id=run.id,
        changes={"source_id": str(run.source_id)},
    )
    await db.commit()
    return ReplayResponse(replayed=True, run_id=run.id, source_id=run.source_id)


@router.post("/sources/{source_id}/reparse", response_model=ReparseResponse)
async def reparse_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Re-parse stored raw HTML after a parser improvement."""
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    result = await db.execute(
        select(Job).where(Job.source_id == source.id, Job.raw_html.is_not(None))
    )
    jobs = result.scalars().all()
    scraper = get_scraper(source.type)

    updated = 0
    for job in jobs:
        page = ScrapedPage(
            html_content=job.raw_html or "",
            status_code=200,
            final_url=job.url or source.url,
        )
        try:
            raw_jobs = scraper.parse(page)
        except Exception:  # noqa: BLE001 - a bad stored page is skipped
            continue
        if not raw_jobs:
            continue
        normalized = scraper.normalize(raw_jobs)
        if not normalized:
            continue
        best = normalized[0]
        job.title = best["title"]
        job.company = best["company"]
        job.description = best.get("description", job.description)
        job.tags = best.get("tags") or job.tags
        updated += 1

    await log_audit(
        db,
        user_id=admin.id,
        action="reparse",
        entity_type="reprocessing",
        entity_id=source.id,
        changes={"reparse_count": updated},
    )
    await db.commit()
    return ReparseResponse(source_id=source.id, reparse_count=updated)


@router.post("/sources/{source_id}/scrape", status_code=status.HTTP_202_ACCEPTED)
async def trigger_scrape(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Manually enqueue a scrape for one source."""
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    enqueue_scrape(str(source.id))
    await log_audit(
        db,
        user_id=admin.id,
        action="trigger_scrape",
        entity_type="reprocessing",
        entity_id=source.id,
    )
    await db.commit()
    return {"enqueued": True, "source_id": str(source.id)}
