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

from app.models import Job, ScrapeRun, Source, SourceAuth
from app.services.secrets import encrypt_secret
from tests.helpers import create_user


class FakeScraper:
    """Deterministic scraper that never touches the network."""

    def __init__(self, jobs: list[RawJob], *, fail: bool = False):
        self.jobs = jobs
        self.fail = fail

    async def fetch(self, url: str, **kwargs) -> ScrapedPage:
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

    def first_fetch_url(self, url: str) -> str:
        return url

    async def discover_urls(self, page: ScrapedPage) -> list[str]:
        return []

    def next_page_url(self, page: ScrapedPage) -> str | None:
        return None


class FakeDiscoveryScraper(FakeScraper):
    """Two-stage scraper: a results page yields detail URLs to fetch."""

    def __init__(self, detail_urls: list[str]):
        super().__init__([])
        self.detail_urls = detail_urls
        self.fetched: list[str] = []

    def first_fetch_url(self, url: str) -> str:
        return "https://engine.example/results"

    async def fetch(self, url: str, **kwargs) -> ScrapedPage:
        self.fetched.append(url)
        return ScrapedPage(html_content="<html></html>", status_code=200, final_url=url)

    async def discover_urls(self, page: ScrapedPage) -> list[str]:
        if page.final_url.startswith("https://engine.example"):
            return self.detail_urls
        return []

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        return [
            RawJob(
                title=f"Job for {page.final_url}",
                company="Acme",
                url=page.final_url,
            )
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
    """Replace the scrape task's scraper lookup + event publisher.

    Also stubs the robots.txt check so tests never touch the network.
    """
    fake = FakeScraper(jobs, fail=fail)
    monkeypatch.setattr(scrape_module, "get_scraper", lambda source, api_key=None: fake)
    monkeypatch.setattr(scrape_module, "publish_job_new", lambda event: None)
    monkeypatch.setattr(scrape_module, "is_allowed_by_robots", lambda url: True)
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


async def test_scrape_skips_when_robots_disallows(
    test_engine, db_session, monkeypatch, redis_client
):
    """A robots.txt ``Disallow`` records a skipped run, never a failure."""
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    await _install_fake_scraper(monkeypatch, SAMPLE_JOBS)
    monkeypatch.setattr(scrape_module, "is_allowed_by_robots", lambda url: False)

    result = await _run_scrape(str(source.id))

    assert result == {
        "source_id": str(source.id),
        "skipped": True,
        "reason": "robots.txt disallows this source",
    }

    runs = (await db_session.execute(select(ScrapeRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "skipped"
    assert "robots.txt" in runs[0].error

    jobs = (await db_session.execute(select(Job))).scalars().all()
    assert jobs == []


async def test_scrape_ignores_robots_when_disabled(
    test_engine, db_session, monkeypatch, redis_client
):
    """With ``respect_robots_txt=False`` the robots check is never consulted."""
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    source.respect_robots_txt = False
    await db_session.commit()
    await _install_fake_scraper(monkeypatch, SAMPLE_JOBS)

    consulted: list[str] = []
    monkeypatch.setattr(
        scrape_module, "is_allowed_by_robots", lambda url: consulted.append(url) or True
    )

    result = await _run_scrape(str(source.id))

    assert result["new"] == 2
    assert consulted == []


async def test_scrape_fetches_discovered_detail_pages(
    test_engine, db_session, monkeypatch, redis_client
):
    """Two-stage discovery: results page links are fetched and capped by max_results."""
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    source.config = {"provider": "google_cse", "max_results": 2}
    await db_session.commit()

    fake = FakeDiscoveryScraper(
        ["https://a.example/j1", "https://b.example/j2", "https://c.example/j3"]
    )
    monkeypatch.setattr(scrape_module, "get_scraper", lambda source, api_key=None: fake)
    monkeypatch.setattr(scrape_module, "publish_job_new", lambda event: None)
    monkeypatch.setattr(scrape_module, "is_allowed_by_robots", lambda url: True)

    result = await _run_scrape(str(source.id))

    assert result["new"] == 2
    # Results page + the two (capped) detail fetches — the third link is dropped.
    assert fake.fetched[0] == "https://engine.example/results"
    assert len(fake.fetched) == 3

    jobs = (await db_session.execute(select(Job))).scalars().all()
    assert len(jobs) == 2
    assert {job.url for job in jobs} == {"https://a.example/j1", "https://b.example/j2"}

    runs = (await db_session.execute(select(ScrapeRun))).scalars().all()
    assert runs[0].status == "success"


async def test_scrape_passes_api_key_to_discovery_scraper(
    test_engine, db_session, monkeypatch, redis_client
):
    """The source's encrypted API key reaches get_scraper for search providers."""
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    source.config = {"provider": "google_cse"}
    await db_session.commit()
    db_session.add(
        SourceAuth(
            source_id=source.id,
            auth_type="api_key",
            credentials_encrypted=encrypt_secret("sk-test-123"),
        )
    )
    await db_session.commit()

    captured: dict = {}
    fake = FakeDiscoveryScraper([])
    monkeypatch.setattr(
        scrape_module,
        "get_scraper",
        lambda source, api_key=None: captured.update(api_key=api_key) or fake,
    )
    monkeypatch.setattr(scrape_module, "publish_job_new", lambda event: None)
    monkeypatch.setattr(scrape_module, "is_allowed_by_robots", lambda url: True)

    await _run_scrape(str(source.id))

    assert captured["api_key"] == "sk-test-123"
