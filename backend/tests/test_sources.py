"""Tests for the sources CRUD API."""

import asyncio

import pytest
from scrapers.aggregator import AGGREGATOR_ADAPTERS
from scrapers.discovery import DISCOVERY_PROVIDERS
from scrapers.types import RawJob, ScrapedPage

from app.config import settings
from app.models.enums import SourceType
from app.routers.sources import _run_preview
from app.services.source_config import (
    adapter_metadata,
    provider_metadata,
    validate_source_config,
)
from tests.helpers import create_user


async def test_list_sources_empty(auth_client):
    client, _, _ = auth_client
    response = await client.get("/api/sources")
    assert response.status_code == 200
    assert response.json() == []


async def test_create_source(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/sources",
        json={
            "name": "Acme Careers",
            "url": "https://acme.example/careers",
            "type": "career_page",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme Careers"
    assert body["type"] == "career_page"
    assert body["health"] == "healthy"
    assert body["id"]
    # Scraping ethics defaults.
    assert body["rate_limit_seconds"] == 30
    assert body["respect_robots_txt"] is True


async def test_scraping_ethics_roundtrip(auth_client):
    """Per-source ethics settings survive create, read and update."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={
            "name": "Polite Agg",
            "url": "https://agg.example",
            "type": "aggregator",
            "rate_limit_seconds": 60,
            "respect_robots_txt": False,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["rate_limit_seconds"] == 60
    assert body["respect_robots_txt"] is False

    source_id = body["id"]
    detail = await client.get(f"/api/sources/{source_id}")
    assert detail.json()["rate_limit_seconds"] == 60
    assert detail.json()["respect_robots_txt"] is False

    updated = await client.put(
        f"/api/sources/{source_id}",
        json={"rate_limit_seconds": 5, "respect_robots_txt": True},
    )
    assert updated.status_code == 200
    assert updated.json()["rate_limit_seconds"] == 5
    assert updated.json()["respect_robots_txt"] is True


async def test_scraping_ethics_validation(auth_client):
    """Negative/absurd rate limits are rejected by the API."""
    client, _, _ = auth_client
    for bad_payload in (
        {"rate_limit_seconds": -1},
        {"rate_limit_seconds": 86401},
    ):
        response = await client.post(
            "/api/sources",
            json={
                "name": "Bad",
                "url": "https://bad.example",
                "type": "rss",
                **bad_payload,
            },
        )
        assert response.status_code == 422


async def test_crud_roundtrip(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={"name": "Agg", "url": "https://agg.example", "type": "aggregator"},
    )
    source_id = created.json()["id"]

    listed = await client.get("/api/sources")
    assert len(listed.json()) == 1

    updated = await client.put(f"/api/sources/{source_id}", json={"name": "Agg2"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Agg2"

    detail = await client.get(f"/api/sources/{source_id}")
    assert detail.json()["name"] == "Agg2"

    deleted = await client.delete(f"/api/sources/{source_id}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/sources/{source_id}")).status_code == 404


async def test_sources_require_auth(client):
    assert (await client.get("/api/sources")).status_code == 401


async def test_providers_endpoint_lists_discovery_providers(auth_client):
    client, _, _ = auth_client
    response = await client.get("/api/sources/providers")
    assert response.status_code == 200
    body = response.json()
    names = {provider["name"] for provider in body}
    # HTML-scraping providers were removed (ToS); the rest are present.
    assert {"ashby", "google_cse", "serpapi", "brightdata"} <= names
    assert not ({"google_html", "bing_html", "duckduckgo_html"} & names)

    for provider in body:
        assert set(provider) == {
            "name",
            "family",
            "requires_key",
            "required_config",
            "required_any",
            "optional_config",
            "example_config",
        }

    ats = next(provider for provider in body if provider["name"] == "ashby")
    assert ats["family"] == "ats"
    assert ats["requires_key"] is False
    assert ats["required_config"] == ["org"]
    assert "company" in ats["optional_config"]
    assert ats["example_config"]["org"]

    search = next(provider for provider in body if provider["name"] == "google_cse")
    assert search["family"] == "search_api"
    assert search["requires_key"] is True
    assert search["required_config"] == ["query", "cx"]

    json_list = next(provider for provider in body if provider["name"] == "json_list")
    assert json_list["required_any"] == [["url", "url_tpl"]]


async def test_user_isolation(auth_client, db_client, db_session):
    """User B must not see sources created by user A."""
    client_a, _, _ = auth_client
    await client_a.post(
        "/api/sources",
        json={"name": "A's source", "url": "https://a.example", "type": "rss"},
    )

    user_b = await create_user(db_session, email="other@example.com")
    login = await db_client.post(
        "/api/auth/login", json={"email": user_b.email, "password": "password123"}
    )
    db_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    listed = await db_client.get("/api/sources")
    assert listed.json() == []


# --- Source preview (dry run) -------------------------------------------------


class _StubScraper:
    """Scraper double: records fetches, returns canned jobs, optionally fails."""

    def __init__(
        self,
        jobs_per_page: int = 1,
        error: Exception | None = None,
        detail_urls: list[str] | None = None,
        delay: float = 0.0,
    ):
        self.fetched: list[str] = []
        self._jobs_per_page = jobs_per_page
        self._error = error
        self._detail_urls = detail_urls or []
        self._delay = delay

    def first_fetch_url(self, url: str) -> str:
        return url

    async def fetch(self, url, *, auth=None):
        self.fetched.append(url)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error is not None:
            raise self._error
        return ScrapedPage(html_content="<html></html>", status_code=200, final_url=url)

    def discover_urls(self, page):
        return self._detail_urls

    def parse(self, page):
        return [
            RawJob(
                title=f"Job {index}",
                company="Acme",
                url=f"{page.final_url}#{index}",
            )
            for index in range(self._jobs_per_page)
        ]

    def normalize(self, raw_jobs):
        return [
            {
                "title": job.title,
                "company": job.company,
                "url": job.url,
                "posted_date": job.posted_date,
                "tags": job.tags,
            }
            for job in raw_jobs
        ]


def _stub_registry(monkeypatch, scraper):
    monkeypatch.setattr(
        "scrapers.registry.get_scraper", lambda source, api_key=None: scraper
    )
    return scraper


async def test_run_preview_returns_sample_and_flags_truncation(monkeypatch):
    _stub_registry(monkeypatch, _StubScraper(jobs_per_page=4))
    monkeypatch.setattr(settings, "scraper_preview_max_jobs", 2)

    response = await _run_preview(
        source_type=SourceType.career_page, url="https://acme.example/jobs", config={}
    )

    assert response.status_code == 200
    assert response.jobs_found == 4
    assert [job.title for job in response.sample_jobs] == ["Job 0", "Job 1"]
    assert response.truncated is True
    assert response.error is None


async def test_run_preview_follows_detail_urls(monkeypatch):
    scraper = _stub_registry(
        monkeypatch,
        _StubScraper(
            jobs_per_page=1,
            detail_urls=["https://acme.example/jobs/1", "https://acme.example/jobs/2"],
        ),
    )
    response = await _run_preview(
        source_type=SourceType.aggregator,
        url="https://acme.example/jobs",
        config={"adapter": "generic_html_list", "detail": True},
    )
    assert scraper.fetched == [
        "https://acme.example/jobs",
        "https://acme.example/jobs/1",
        "https://acme.example/jobs/2",
    ]
    assert response.jobs_found == 2


async def test_run_preview_reports_errors_from_url_rendering():
    """A config mistake in `first_fetch_url` is reported, not raised (no 500)."""
    response = await _run_preview(
        source_type=SourceType.discovery,
        url="https://api.example/jobs",
        config={"provider": "workday", "host": "acme.wd1.myworkdayjobs.com"},
    )
    assert response.jobs_found == 0
    assert response.error is not None
    assert "tenant" in response.error


async def test_run_preview_reports_config_errors():
    """The real registry is used here: discovery without a provider fails fast."""
    response = await _run_preview(
        source_type=SourceType.discovery, url="https://acme.example", config={}
    )
    assert response.jobs_found == 0
    assert response.error is not None
    assert "provider" in response.error


async def test_run_preview_redacts_credentials_in_errors(monkeypatch):
    _stub_registry(
        monkeypatch,
        _StubScraper(error=ValueError("403 for https://acme.example/s?api_key=SECRET")),
    )
    response = await _run_preview(
        source_type=SourceType.career_page, url="https://acme.example", config={}
    )
    assert response.jobs_found == 0
    assert response.error is not None
    assert "SECRET" not in response.error
    assert "REDACTED" in response.error


async def test_run_preview_honours_robots_when_asked(monkeypatch):
    _stub_registry(monkeypatch, _StubScraper())
    monkeypatch.setattr(
        "app.routers.sources.is_allowed_by_robots", lambda url: False
    )
    blocked = await _run_preview(
        source_type=SourceType.career_page,
        url="https://acme.example",
        config={},
        respect_robots=True,
    )
    assert blocked.jobs_found == 0
    assert "robots.txt" in (blocked.error or "")
    # Sources that opted out of robots checks still preview.
    allowed = await _run_preview(
        source_type=SourceType.career_page, url="https://acme.example", config={}
    )
    assert allowed.jobs_found == 1


async def test_run_preview_times_out(monkeypatch):
    _stub_registry(monkeypatch, _StubScraper(delay=0.05))
    monkeypatch.setattr(settings, "scraper_preview_timeout_seconds", 0.01)
    response = await _run_preview(
        source_type=SourceType.career_page, url="https://acme.example", config={}
    )
    assert response.error is not None
    assert "timed out" in response.error


async def test_preview_endpoint_returns_a_sample_without_persisting(
    auth_client, monkeypatch
):
    client, _, _ = auth_client
    _stub_registry(monkeypatch, _StubScraper(jobs_per_page=2))

    response = await client.post(
        "/api/sources/preview",
        json={"url": "https://acme.example/jobs", "type": "career_page"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["jobs_found"] == 2
    assert body["sample_jobs"][0]["title"] == "Job 0"
    assert body["sample_jobs"][0]["company"] == "Acme"
    assert body["error"] is None
    # A dry run writes nothing: no source, no jobs.
    assert (await client.get("/api/sources")).json() == []


async def test_preview_stored_source_is_user_scoped(
    auth_client, db_client, db_session, monkeypatch
):
    client, _, _ = auth_client
    # Stored sources enforce robots.txt; keep the test hermetic (no DNS, no
    # shared robots cache) — the blocked path is covered separately.
    monkeypatch.setattr("app.routers.sources.is_allowed_by_robots", lambda url: True)
    created = await client.post(
        "/api/sources",
        json={
            "name": "Stub board",
            "url": "https://acme.example/jobs",
            "type": "aggregator",
            "config": {"adapter": "generic_html_list"},
        },
    )
    source_id = created.json()["id"]
    _stub_registry(monkeypatch, _StubScraper(jobs_per_page=1))

    mine = await client.post(f"/api/sources/{source_id}/preview")
    assert mine.status_code == 200
    assert mine.json()["error"] is None, mine.json()
    assert mine.json()["jobs_found"] == 1

    user_b = await create_user(db_session, email="previewer@example.com")
    login = await db_client.post(
        "/api/auth/login", json={"email": user_b.email, "password": "password123"}
    )
    db_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    assert (await db_client.post(f"/api/sources/{source_id}/preview")).status_code == 404


async def test_preview_requires_auth(client):
    response = await client.post(
        "/api/sources/preview",
        json={"url": "https://acme.example/jobs", "type": "career_page"},
    )
    assert response.status_code == 401


# --- Config metadata + validation ---------------------------------------------


def test_validator_accepts_valid_configs():
    validate_source_config(SourceType.discovery, {"provider": "ashby", "org": "acme"})
    validate_source_config(
        SourceType.discovery,
        {"provider": "json_list", "url_tpl": "https://x.example/{tag}", "tag": "python"},
    )
    validate_source_config(SourceType.aggregator, {"adapter": "generic_html_list"})
    validate_source_config(SourceType.aggregator, None)
    # Non-dispatching source types take no config at all.
    validate_source_config(SourceType.rss, None)
    validate_source_config(SourceType.career_page, {"anything": "goes"})


def test_validator_reports_missing_and_unknown_keys():
    with pytest.raises(ValueError, match="provider"):
        validate_source_config(SourceType.discovery, {})
    with pytest.raises(ValueError, match="unknown discovery provider"):
        validate_source_config(SourceType.discovery, {"provider": "does-not-exist"})
    # Only the keys that are actually absent are reported.
    with pytest.raises(ValueError, match="tenant, site"):
        validate_source_config(
            SourceType.discovery, {"provider": "workday", "host": "acme.example"}
        )
    with pytest.raises(ValueError, match="url or url_tpl"):
        validate_source_config(
            SourceType.discovery, {"provider": "json_list", "items_path": "items"}
        )
    with pytest.raises(ValueError, match="unknown aggregator adapter"):
        validate_source_config(SourceType.aggregator, {"adapter": "does-not-exist"})


def test_provider_metadata_covers_every_registered_provider():
    """Every provider publishes a well-formed contract that its example satisfies."""
    body = provider_metadata()
    assert {item["name"] for item in body} == set(DISCOVERY_PROVIDERS)
    for item in body:
        assert isinstance(item["required_config"], list)
        assert isinstance(item["optional_config"], list)
        assert isinstance(item["example_config"], dict)
        for group in item["required_any"]:
            assert isinstance(group, list) and group
        if item["example_config"]:
            validate_source_config(
                SourceType.discovery,
                {"provider": item["name"], **item["example_config"]},
            )


def test_adapter_metadata_covers_every_registered_adapter():
    body = adapter_metadata()
    assert {item["name"] for item in body} == set(AGGREGATOR_ADAPTERS)
    for item in body:
        assert item["description"]
        for group in item["required_any"]:
            assert isinstance(group, list) and group
        validate_source_config(
            SourceType.aggregator,
            {"adapter": item["name"], **item["example_config"]},
        )


async def test_create_source_rejects_invalid_config(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/sources",
        json={
            "name": "Bad discovery",
            "url": "https://acme.example/jobs",
            "type": "discovery",
            "config": {},
        },
    )
    assert response.status_code == 422
    assert "provider" in response.json()["detail"]


async def test_update_source_validates_the_effective_config(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={
            "name": "Greenhouse board",
            "url": "https://acme.example/jobs",
            "type": "discovery",
            "config": {"provider": "greenhouse", "board_token": "acme"},
        },
    )
    assert created.status_code == 201
    source_id = created.json()["id"]

    # Dropping the required key via an update is rejected...
    bad = await client.put(
        f"/api/sources/{source_id}", json={"config": {"provider": "greenhouse"}}
    )
    assert bad.status_code == 422
    assert "board_token" in bad.json()["detail"]

    # ...while a valid change (merged with the stored config) goes through.
    ok = await client.put(
        f"/api/sources/{source_id}",
        json={"config": {"provider": "greenhouse", "board_token": "other"}},
    )
    assert ok.status_code == 200
    assert ok.json()["config"]["board_token"] == "other"


async def test_adapters_endpoint_lists_aggregator_adapters(auth_client):
    client, _, _ = auth_client
    response = await client.get("/api/sources/adapters")
    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body] == [
        "generic_html_list",
        "embedded_json_list",
    ]
    assert all(item["description"] for item in body)
    assert "item_selector" in body[0]["optional_config"]
    assert body[0]["example_config"]["item_selector"]
