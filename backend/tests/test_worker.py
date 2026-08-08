"""Integration tests for the scraping pipeline and resilience primitives.

Requires PostgreSQL (test DB) and Redis; skipped when unavailable.
"""

import pytest
from scrapers.types import RawJob, ScrapedPage
from sqlalchemy import select
from workers.resilience import (
    circuit_breaker_is_open,
    circuit_breaker_record_failure,
    circuit_breaker_reset,
    rate_limit_mark,
    rate_limit_wait,
)
from workers.tasks import scrape as scrape_module
from workers.tasks.scrape import _run_scrape

from app.models import Job, ScrapeRun, Source
from tests.helpers import create_user


class FakeScraper:
    """Deterministic scraper that never touches the network."""

    def __init__(self, jobs: list[RawJob], *, fail: bool = False):
        self.jobs = jobs
        self.fail = fail

    async def fetch(self, url: str) -> ScrapedPage:
        return ScrapedPage(html_content="<html></html>", status_code=200, final_url=url)

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        if self.fail:
            raise RuntimeError("boom")
        return self.jobs

    def normalize(self, raw_jobs: list[RawJob]) -> list[dict]:
        return [
            {
                "title": j.title,
                "company": j.company,
                "url": j.url,
                "description": j.description,
                "posted_date": None,
                "tags": j.tags,
            }
            for j in raw_jobs
        ]


SAMPLE_JOBS = [
    RawJob(title="Backend Engineer", company="Acme", url="https://acme.example/jobs/1"),
    RawJob(title="Data Engineer", company="Acme", url="https://acme.example/jobs/2"),
]


async def _make_source(db_session, user) -> Source:
    source = Source(
        user_id=user.id,
        name="Acme",
        url="https://acme.example/careers",
        type="career_page",
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


async def _install_fake_scraper(monkeypatch, jobs, *, fail=False):
    """Replace the scrape task's scraper lookup + event publisher."""
    fake = FakeScraper(jobs, fail=fail)
    monkeypatch.setattr(scrape_module, "get_scraper", lambda source_type: fake)
    monkeypatch.setattr(scrape_module, "publish_job_new", lambda event: None)
    return fake


async def test_scrape_pipeline_stores_jobs_and_records_run(
    test_engine, db_session, monkeypatch, redis_client
):
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    await _install_fake_scraper(monkeypatch, SAMPLE_JOBS)

    result = await _run_scrape(str(source.id))

    assert result["new"] == 2
    assert result["skipped"] == 0

    jobs = (await db_session.execute(select(Job))).scalars().all()
    assert len(jobs) == 2
    assert {job.url for job in jobs} == {"https://acme.example/jobs/1", "https://acme.example/jobs/2"}

    runs = (await db_session.execute(select(ScrapeRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "success"
    assert runs[0].new_jobs == 2

    # Reload the source from the DB (refresh is async-safe; get() would
    # return the stale identity-map instance).
    await db_session.refresh(source)
    assert source.last_scraped is not None
    assert source.health == "healthy"


async def test_scrape_deduplicates_on_second_run(
    test_engine, db_session, monkeypatch, redis_client
):
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    await _install_fake_scraper(monkeypatch, SAMPLE_JOBS)

    first = await _run_scrape(str(source.id))
    second = await _run_scrape(str(source.id))

    assert first["new"] == 2
    assert second["new"] == 0
    assert second["skipped"] == 2

    jobs = (await db_session.execute(select(Job))).scalars().all()
    assert len(jobs) == 2


async def test_scrape_failure_records_run_and_opens_circuit_breaker(
    test_engine, db_session, monkeypatch, redis_client
):
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    await _install_fake_scraper(monkeypatch, [], fail=True)
    circuit_breaker_reset(str(source.id))

    with pytest.raises(RuntimeError):
        await _run_scrape(str(source.id))

    runs = (await db_session.execute(select(ScrapeRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert runs[0].error == "boom"

    assert circuit_breaker_is_open(str(source.id)) is False  # one failure only


async def test_circuit_breaker_opens_after_threshold(redis_client):
    source_id = "11111111-1111-1111-1111-111111111111"
    circuit_breaker_reset(source_id)
    assert circuit_breaker_is_open(source_id) is False

    for _ in range(5):
        circuit_breaker_record_failure(source_id)

    assert circuit_breaker_is_open(source_id) is True
    circuit_breaker_reset(source_id)
    assert circuit_breaker_is_open(source_id) is False


async def test_rate_limit_mark_and_wait(redis_client):
    url = "https://acme.example/careers"
    assert rate_limit_wait(url, cooldown_seconds=60) == 0.0
    rate_limit_mark(url, cooldown_seconds=60)
    assert rate_limit_wait(url, cooldown_seconds=60) > 0.0
