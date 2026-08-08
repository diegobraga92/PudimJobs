"""Tests verifying resilience behaviours that the chaos experiments exercise.

These cover the API/DB-level guarantees the scripts assert live:
circuit-breaker blocking, idempotent dedup, and idempotent quality
re-assessment.
"""

from datetime import date

import pytest
from scrapers.types import RawJob, ScrapedPage
from sqlalchemy import select
from workers.resilience import (
    CircuitBreakerOpenError,
    circuit_breaker_is_open,
    circuit_breaker_record_failure,
    circuit_breaker_reset,
)
from workers.tasks.quality import _assess_quality
from workers.tasks.scrape import _run_scrape

from app.models import Job, ScrapeQuality, ScrapeRun, Source
from tests.helpers import create_user


class FakeScraper:
    async def fetch(self, url: str) -> ScrapedPage:
        return ScrapedPage(html_content="<html></html>", status_code=200, final_url=url)

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        return [RawJob(title="Python Engineer", company="Acme", url="https://acme.example/jobs/1")]

    def normalize(self, raw_jobs: list[RawJob]) -> list[dict]:
        return [
            {
                "title": r.title,
                "company": r.company,
                "url": r.url,
                "description": None,
                "posted_date": None,
                "tags": [],
            }
            for r in raw_jobs
        ]


async def test_circuit_breaker_blocks_scrape_with_skipped_run(
    test_engine, db_session, monkeypatch, redis_client
):
    user = await create_user(db_session)
    source = Source(user_id=user.id, name="Acme", url="https://acme.example", type="rss")
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    # Open the breaker for this source (5 failures threshold).
    circuit_breaker_reset(str(source.id))
    for _ in range(5):
        circuit_breaker_record_failure(str(source.id))
    assert circuit_breaker_is_open(str(source.id)) is True

    monkeypatch.setattr("workers.tasks.scrape.get_scraper", lambda _t: FakeScraper())
    monkeypatch.setattr("workers.tasks.scrape.publish_job_new", lambda _e: None)

    with pytest.raises(CircuitBreakerOpenError):
        await _run_scrape(str(source.id))

    runs = (await db_session.execute(select(ScrapeRun))).scalars().all()
    assert runs[-1].status == "skipped"
    assert runs[-1].error == "circuit breaker open"


async def test_quality_reassessment_is_idempotent(test_engine, db_session):
    """Re-running the quality task upserts one row, never duplicates."""
    user = await create_user(db_session)
    job = Job(
        user_id=user.id,
        title="Backend Engineer",
        company="Google LLC",
        description="x" * 300,
        posted_date=date(2026, 8, 1),
        tags=["react.js"],
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    first = await _assess_quality(str(job.id))
    second = await _assess_quality(str(job.id))

    rows = (await db_session.execute(select(ScrapeQuality))).scalars().all()
    assert len(rows) == 1
    assert first["normalized_company"] == "Google"
    assert second["normalized_company"] == "Google"

    await db_session.refresh(job)
    assert "react" in job.tags  # skill normalization applied in place
