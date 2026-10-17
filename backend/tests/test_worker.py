"""Integration tests for the scraping pipeline and resilience primitives.

Requires PostgreSQL (test DB) and Redis; skipped when unavailable.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

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

from app.models import Job, Notification, ScrapeRun, Source, SourceAuth
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
                "external_id": j.external_id,
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


async def _make_source(db_session, user, **overrides) -> Source:
    values = {
        "user_id": user.id,
        "name": "Acme",
        "url": "https://acme.example/careers",
        "type": "career_page",
    }
    values.update(overrides)
    source = Source(**values)
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
    assert {job.url for job in jobs} == {
        "https://acme.example/jobs/1",
        "https://acme.example/jobs/2",
    }

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


async def test_scrape_fails_fast_on_empty_parse(test_engine, db_session, monkeypatch, redis_client):
    """A completed scrape that parses zero jobs fails instead of '0 new'."""
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    await _install_fake_scraper(monkeypatch, [])

    with pytest.raises(scrape_module.EmptyScrapeError):
        await _run_scrape(str(source.id))

    runs = (await db_session.execute(select(ScrapeRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert "0 jobs" in runs[0].error


async def test_scrape_allow_empty_config_permits_empty_sources(
    test_engine, db_session, monkeypatch, redis_client
):
    """``config['allow_empty']=true`` opts out of the empty-parse fail-fast."""
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    source.config = {"allow_empty": True}
    await db_session.commit()
    await _install_fake_scraper(monkeypatch, [])

    result = await _run_scrape(str(source.id))

    assert result["new"] == 0
    runs = (await db_session.execute(select(ScrapeRun))).scalars().all()
    assert runs[0].status == "success"


async def test_scrape_deduplicates_by_external_id(
    test_engine, db_session, monkeypatch, redis_client
):
    """Provider-native ids dedupe re-postings that reuse a URL."""
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    job = RawJob(
        title="Backend Engineer",
        company="Acme",
        url="https://acme.example/jobs/evergreen",
        external_id="acme-req-1",
    )
    await _install_fake_scraper(monkeypatch, [job])

    first = await _run_scrape(str(source.id))
    second = await _run_scrape(str(source.id))

    assert first["new"] == 1
    assert second["new"] == 0
    assert second["skipped"] == 1

    jobs = (await db_session.execute(select(Job))).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].external_id == "acme-req-1"


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
    source.config = {"provider": "google_cse", "allow_empty": True}
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


class KeyedScraper(FakeDiscoveryScraper):
    """Discovery scraper that records the credential check the worker makes."""

    def __init__(self) -> None:
        super().__init__([])
        self.checked: list[bool] = []

    def check_credentials(self, has_api_key: bool) -> None:
        self.checked.append(has_api_key)
        if not has_api_key:
            raise ValueError("jsearch needs an API key — add one in the Authentication panel")


async def test_scrape_skips_a_keyed_provider_without_a_key(
    test_engine, db_session, monkeypatch, redis_client
):
    """No key on a keyed provider: skip with the reason, never call the vendor."""
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    source.config = {"provider": "jsearch", "query": "python"}
    await db_session.commit()

    fake = KeyedScraper()
    monkeypatch.setattr(scrape_module, "get_scraper", lambda source, api_key=None: fake)

    result = await _run_scrape(str(source.id))

    assert fake.checked == [False]
    assert result["skipped"] is True
    assert "API key" in result["reason"]
    assert fake.fetched == []

    runs = (await db_session.execute(select(ScrapeRun))).scalars().all()
    assert runs[0].status == "skipped"
    assert "API key" in runs[0].error


async def test_scrape_checks_credentials_through_the_real_registry(
    test_engine, db_session, monkeypatch, redis_client
):
    """A real discovery source (no stored key) is skipped before any fetch."""
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    source.type = "discovery"
    source.config = {"provider": "jsearch", "query": "python"}
    await db_session.commit()

    fetched: list[str] = []
    monkeypatch.setattr(
        scrape_module,
        "is_allowed_by_robots",
        lambda url: fetched.append(url) or True,
    )

    result = await _run_scrape(str(source.id))

    assert result["skipped"] is True
    assert "API key" in result["reason"]
    assert fetched == []  # not even the robots check ran


async def test_scrape_skips_the_credential_check_when_a_key_is_stored(
    test_engine, db_session, monkeypatch, redis_client
):
    """A stored key short-circuits the check, so the run proceeds normally."""
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    source.config = {"provider": "jsearch", "query": "python", "allow_empty": True}
    await db_session.commit()
    db_session.add(
        SourceAuth(
            source_id=source.id,
            auth_type="api_key",
            credentials_encrypted=encrypt_secret("sk-good-123"),
        )
    )
    await db_session.commit()

    fake = KeyedScraper()
    monkeypatch.setattr(scrape_module, "get_scraper", lambda source, api_key=None: fake)
    monkeypatch.setattr(scrape_module, "publish_job_new", lambda event: None)
    monkeypatch.setattr(scrape_module, "is_allowed_by_robots", lambda url: True)

    result = await _run_scrape(str(source.id))

    assert result["new"] == 1  # the results page itself yields one job
    assert fake.checked == []
    assert fake.fetched == ["https://engine.example/results"]

    runs = (await db_session.execute(select(ScrapeRun))).scalars().all()
    assert runs[0].status == "success"


# --- Pagination (url-based, body-based, and the same-URL guard) ---------------


class FakePaginatingScraper(FakeScraper):
    """Serves listing pages, with or without changing the URL each time."""

    def __init__(self, pages: int, *, repeat_url: bool = False, body_paging: bool = False):
        super().__init__([])
        self.pages = pages
        self.repeat_url = repeat_url
        self.pagination_in_body = body_paging
        self.fetched: list[str] = []
        self.served = 0

    def first_fetch_url(self, url: str) -> str:
        return "https://board.example/jobs?page=1"

    async def fetch(self, url: str, **kwargs) -> ScrapedPage:
        self.fetched.append(url)
        return ScrapedPage(html_content="<html></html>", status_code=200, final_url=url)

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        return []

    def next_page_url(self, page: ScrapedPage) -> str | None:
        self.served += 1
        if self.served >= self.pages:
            return None
        if self.repeat_url:
            return page.final_url
        return f"https://board.example/jobs?page={self.served + 1}"


async def _run_pagination(monkeypatch, db_session, fake, config):
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    source.config = {"allow_empty": True, **config}
    await db_session.commit()
    monkeypatch.setattr(scrape_module, "get_scraper", lambda source, api_key=None: fake)
    monkeypatch.setattr(scrape_module, "publish_job_new", lambda event: None)
    monkeypatch.setattr(scrape_module, "is_allowed_by_robots", lambda url: True)
    await _run_scrape(str(source.id))
    return fake


async def test_scrape_paginates_listing_urls_up_to_max_pages(
    test_engine, db_session, monkeypatch, redis_client
):
    fake = await _run_pagination(
        monkeypatch, db_session, FakePaginatingScraper(5), {"max_pages": 3}
    )
    assert fake.fetched == [
        "https://board.example/jobs?page=1",
        "https://board.example/jobs?page=2",
        "https://board.example/jobs?page=3",
    ]


async def test_scrape_follows_repeated_urls_when_the_provider_pages_by_body(
    test_engine, db_session, monkeypatch, redis_client
):
    """Jooble-style POST providers keep the URL and move the page in the body."""
    fake = await _run_pagination(
        monkeypatch,
        db_session,
        FakePaginatingScraper(5, repeat_url=True, body_paging=True),
        {"max_pages": 2},
    )
    assert fake.fetched == ["https://board.example/jobs?page=1"] * 2


async def test_scrape_stops_when_a_paginator_keeps_returning_the_same_url(
    test_engine, db_session, monkeypatch, redis_client
):
    """An unchanged URL means "no more pages" unless the provider says otherwise."""
    fake = await _run_pagination(
        monkeypatch, db_session, FakePaginatingScraper(5, repeat_url=True), {"max_pages": 3}
    )
    assert fake.fetched == ["https://board.example/jobs?page=1"]


@pytest.mark.parametrize(
    ("cap", "config", "expected"),
    (
        # No `max_results`: the provider's own cap keeps paid fetches short.
        (5, {}, 5),
        # An explicit `max_results` always wins over the provider's default.
        (5, {"max_results": 2}, 2),
        (5, {"max_results": 9}, 9),
    ),
)
async def test_scrape_caps_detail_fetches_by_the_providers_default(
    test_engine, db_session, monkeypatch, redis_client, cap, config, expected
):
    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    source.config = {"provider": "serpapi", "allow_empty": True, **config}
    await db_session.commit()

    links = [f"https://paid.example/j{index}" for index in range(12)]
    fake = FakeDiscoveryScraper(links)
    fake.default_max_results = cap
    monkeypatch.setattr(scrape_module, "get_scraper", lambda source, api_key=None: fake)
    monkeypatch.setattr(scrape_module, "publish_job_new", lambda event: None)
    monkeypatch.setattr(scrape_module, "is_allowed_by_robots", lambda url: True)

    await _run_scrape(str(source.id))

    # The results page plus the capped detail fetches, in order.
    assert fake.fetched == ["https://engine.example/results", *links[:expected]]


# --- Manual (watchlist) sources (ADR 018) ------------------------------------


async def _make_manual_source(db_session, user, **config) -> Source:
    """A hand-checked watchlist source (never fetched by the engine)."""
    source = Source(
        user_id=user.id,
        name="Watchlist",
        url="https://protected.example/jobs",
        type="manual",
        config={"cadence_days": 7, **config},
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


async def test_scrape_skips_manual_sources_without_fetching(
    test_engine, db_session, monkeypatch, redis_client
):
    """A manual source records a skipped run and never reaches a scraper."""
    user = await create_user(db_session)
    source = await _make_manual_source(db_session, user)

    def _never_looked_up(source, api_key=None):  # pragma: no cover - must not run
        raise AssertionError("manual sources must not reach the scraper registry")

    monkeypatch.setattr(scrape_module, "get_scraper", _never_looked_up)
    monkeypatch.setattr(scrape_module, "is_allowed_by_robots", lambda url: True)

    result = await _run_scrape(str(source.id))

    assert result == {
        "source_id": str(source.id),
        "skipped": True,
        "reason": "manual source; check it by hand",
    }

    runs = (await db_session.execute(select(ScrapeRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "skipped"
    assert "manual" in runs[0].error

    # Nothing was collected and the hand-check timestamp is untouched.
    assert (await db_session.execute(select(Job))).scalars().all() == []
    await db_session.refresh(source)
    assert source.last_scraped is None


async def test_sweep_schedules_scraped_sources_and_reminds_manual_ones(
    test_engine, db_session, monkeypatch, redis_client
):
    """The sweeper enqueues scrapeable sources and reminds due watchlist ones."""
    from workers.tasks import sweep as sweep_module

    user = await create_user(db_session)
    scrapeable = await _make_source(db_session, user)  # never scraped → due
    manual = await _make_manual_source(
        db_session, user, next_check_at="2020-01-01T00:00:00+00:00"
    )

    scheduled: list[str] = []
    monkeypatch.setattr(
        scrape_module,
        "scrape_source",
        SimpleNamespace(delay=lambda source_id: scheduled.append(source_id)),
    )

    first = await sweep_module._sweep()

    assert first == {"due": 1, "scheduled": 1, "reminded": 1}
    # Only the scrapeable source is enqueued: the manual one is hand-checked.
    assert scheduled == [str(scrapeable.id)]

    notifications = (await db_session.execute(select(Notification))).scalars().all()
    assert len(notifications) == 1
    assert notifications[0].user_id == user.id
    assert notifications[0].channel == "in_app"
    assert manual.name in notifications[0].title

    # A second sweep must not remind the same due period again.
    second = await sweep_module._sweep()
    assert second["reminded"] == 0
    assert len((await db_session.execute(select(Notification))).scalars().all()) == 1


async def test_sweep_respects_per_source_scrape_interval(
    test_engine, db_session, monkeypatch, redis_client
):
    """A weekly source is skipped until its interval elapses; others stay hourly."""
    from workers.tasks import sweep as sweep_module

    user = await create_user(db_session)
    now = datetime.now(UTC)

    weekly_recent = await _make_source(
        db_session,
        user,
        name="Weekly recent",
        scrape_interval_minutes=10080,
        last_scraped=now - timedelta(days=2),
    )
    weekly_stale = await _make_source(
        db_session,
        user,
        name="Weekly stale",
        scrape_interval_minutes=10080,
        last_scraped=now - timedelta(days=9),
    )
    # No per-source interval: the global 60-minute freshness still applies.
    await _make_source(
        db_session,
        user,
        name="Default recent",
        last_scraped=now - timedelta(minutes=30),
    )
    default_stale = await _make_source(
        db_session,
        user,
        name="Default stale",
        last_scraped=now - timedelta(hours=2),
    )
    await db_session.commit()

    scheduled: list[str] = []
    monkeypatch.setattr(
        scrape_module,
        "scrape_source",
        SimpleNamespace(delay=lambda source_id: scheduled.append(source_id)),
    )

    result = await sweep_module._sweep()

    assert result["due"] == 2
    assert result["scheduled"] == 2
    assert set(scheduled) == {str(weekly_stale.id), str(default_stale.id)}
    assert str(weekly_recent.id) not in scheduled


async def test_sweep_ignores_manual_sources_that_are_not_due_yet(
    test_engine, db_session, monkeypatch, redis_client
):
    """A freshly created watchlist source is not reminded before it is due."""
    from workers.tasks import sweep as sweep_module

    user = await create_user(db_session)
    manual = await _make_manual_source(db_session, user)  # due in 7 days

    monkeypatch.setattr(
        scrape_module,
        "scrape_source",
        SimpleNamespace(delay=lambda source_id: None),
    )

    result = await sweep_module._sweep()

    assert result == {"due": 0, "scheduled": 0, "reminded": 0}
    assert (await db_session.execute(select(Notification))).scalars().all() == []
    await db_session.refresh(manual)
    assert manual.config.get("reminded_at") is None


async def test_hand_check_clears_the_reminder_and_reschedules(
    test_engine, db_session, monkeypatch, redis_client
):
    """Checking a due source by hand clears its reminder state for the period."""
    from workers.tasks import sweep as sweep_module

    from app.models.enums import SourceType
    from app.services.source_watchlist import advance_manual_check, is_due, was_reminded

    user = await create_user(db_session)
    manual = await _make_manual_source(
        db_session, user, next_check_at="2020-01-01T00:00:00+00:00"
    )

    monkeypatch.setattr(
        scrape_module, "scrape_source", SimpleNamespace(delay=lambda source_id: None)
    )
    assert (await sweep_module._sweep())["reminded"] == 1
    await db_session.refresh(manual)
    assert was_reminded(manual) is True

    # The user opens the board and marks it checked.
    advance_manual_check(manual)
    await db_session.commit()
    await db_session.refresh(manual)

    assert manual.type == SourceType.manual
    assert manual.last_scraped is not None
    assert was_reminded(manual) is False
    assert is_due(manual) is False

    # The next sweep has nothing to remind until the new due date arrives.
    assert (await sweep_module._sweep())["reminded"] == 0


async def test_sweep_never_reminds_an_avoided_source(
    test_engine, db_session, monkeypatch, redis_client
):
    """An avoided watchlist source is silent until it is restored (ADR 019)."""
    from workers.tasks import sweep as sweep_module

    from app.services.source_watchlist import set_avoided

    user = await create_user(db_session)
    manual = await _make_manual_source(
        db_session, user, next_check_at="2020-01-01T00:00:00+00:00"
    )
    set_avoided(manual, True, "recruiter spam")
    await db_session.commit()

    monkeypatch.setattr(
        scrape_module, "scrape_source", SimpleNamespace(delay=lambda source_id: None)
    )

    avoided_sweep = await sweep_module._sweep()

    assert avoided_sweep == {"due": 0, "scheduled": 0, "reminded": 0}
    assert (await db_session.execute(select(Notification))).scalars().all() == []
    await db_session.refresh(manual)
    # No reminder was recorded either, so nothing is deduplicated away.
    assert manual.config.get("reminded_at") is None

    # Restoring the source re-arms exactly one nudge for the overdue period.
    set_avoided(manual, False)
    await db_session.commit()

    assert (await sweep_module._sweep())["reminded"] == 1
    notifications = (await db_session.execute(select(Notification))).scalars().all()
    assert len(notifications) == 1
    assert manual.name in notifications[0].title


async def test_sweep_never_schedules_an_avoided_source(
    test_engine, db_session, monkeypatch, redis_client
):
    """Avoided applies to scraped sources too: nothing is enqueued."""
    from workers.tasks import sweep as sweep_module

    from app.services.source_watchlist import set_avoided

    user = await create_user(db_session)
    avoided = await _make_source(db_session, user)
    set_avoided(avoided, True, "duplicates")
    active = await _make_source(db_session, user)
    active.name = "Keep me"
    await db_session.commit()

    scheduled: list[str] = []
    monkeypatch.setattr(
        scrape_module,
        "scrape_source",
        SimpleNamespace(delay=lambda source_id: scheduled.append(source_id)),
    )

    result = await sweep_module._sweep()

    assert result["due"] == 1
    assert scheduled == [str(active.id)]


async def test_scrape_skips_avoided_sources_without_fetching(
    test_engine, db_session, monkeypatch, redis_client
):
    """A direct invocation records a skip carrying the user's reason."""
    from app.services.source_watchlist import set_avoided

    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    set_avoided(source, True, "scammy postings")
    await db_session.commit()

    def _never_looked_up(source, api_key=None):  # pragma: no cover - must not run
        raise AssertionError("avoided sources must not reach the scraper registry")

    monkeypatch.setattr(scrape_module, "get_scraper", _never_looked_up)

    result = await _run_scrape(str(source.id))

    assert result == {
        "source_id": str(source.id),
        "skipped": True,
        "reason": "scammy postings",
    }


async def test_scrape_skip_has_a_default_reason_without_one(
    test_engine, db_session, monkeypatch, redis_client
):
    """Avoiding without a reason still explains the skip in the run log."""
    from app.services.source_watchlist import set_avoided

    user = await create_user(db_session)
    source = await _make_source(db_session, user)
    set_avoided(source, True)
    await db_session.commit()

    monkeypatch.setattr(
        scrape_module,
        "get_scraper",
        lambda source, api_key=None: (_ for _ in ()).throw(AssertionError("no fetch")),
    )

    result = await _run_scrape(str(source.id))

    assert result["skipped"] is True
    assert "avoided" in result["reason"]
