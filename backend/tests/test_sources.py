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
    manual_metadata,
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
    monkeypatch.setattr("scrapers.registry.get_scraper", lambda source, api_key=None: scraper)
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
    monkeypatch.setattr("app.routers.sources.is_allowed_by_robots", lambda url: False)
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


async def test_preview_endpoint_returns_a_sample_without_persisting(auth_client, monkeypatch):
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
    # Manual watchlist sources only need a cadence (and free-form notes).
    validate_source_config(SourceType.manual, None)
    validate_source_config(SourceType.manual, {"cadence_days": 1, "notes": "watch here"})
    validate_source_config(SourceType.manual, {"cadence_days": 365})
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


def test_validator_checks_the_request_shape_of_keyed_providers():
    """Keyed APIs build URLs/bodies at save time, so mistakes fail fast."""
    base = {"provider": "json_list", "url": "https://api.example/jobs"}

    with pytest.raises(ValueError, match="unsupported method"):
        validate_source_config(SourceType.discovery, {**base, "method": "PUT"})
    with pytest.raises(ValueError, match="'method: POST' requires a 'body'"):
        validate_source_config(SourceType.discovery, {**base, "method": "POST"})
    with pytest.raises(ValueError, match="must be one of"):
        validate_source_config(
            SourceType.discovery, {**base, "auth": {"in": "cookie", "name": "k"}}
        )
    # A placeholder with no matching config key is reported too.
    with pytest.raises(ValueError, match="board"):
        validate_source_config(
            SourceType.discovery, {"provider": "json_list", "url_tpl": "https://x/{board}"}
        )

    # A valid POST shape and a *missing key* both save fine: the key is a
    # credential, added in the Authentication panel right after creation.
    validate_source_config(
        SourceType.discovery,
        {
            **base,
            "method": "POST",
            "body": {"q": "{query}", "page": "{page}"},
            "auth": {"in": "header", "name": "X-API-Key"},
            "query": "python",
        },
    )
    validate_source_config(SourceType.discovery, {"provider": "jooble", "query": "python"})


def test_manual_metadata_matches_the_validator():
    """What the endpoint publishes is exactly what the validator enforces."""
    meta = manual_metadata()
    bounds = meta["cadence_days"]

    assert meta["type"] == "manual"
    assert bounds == {"default": 7, "min": 1, "max": 365}
    assert meta["required_config"] == []
    assert meta["optional_config"] == ["cadence_days", "notes"]
    assert meta["example_config"]["cadence_days"] == bounds["default"]
    validate_source_config(SourceType.manual, {"cadence_days": bounds["min"]})
    validate_source_config(SourceType.manual, {"cadence_days": bounds["max"]})
    for out_of_range in (bounds["min"] - 1, bounds["max"] + 1):
        with pytest.raises(ValueError, match="cadence_days"):
            validate_source_config(SourceType.manual, {"cadence_days": out_of_range})


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
    bad = await client.put(f"/api/sources/{source_id}", json={"config": {"provider": "greenhouse"}})
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


# --- Manual (watchlist) sources (ADR 018) -------------------------------------


async def test_create_manual_source_exposes_its_schedule(auth_client):
    """A manual source is never fetched; it reports when it is next due."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={
            "name": "Login-walled board",
            "url": "https://protected.example/jobs",
            "type": "manual",
            "config": {"cadence_days": 3},
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["type"] == "manual"
    # Nothing was fetched: the board is hand-checked.
    assert body["last_scraped"] is None
    assert body["due"] is False
    assert body["next_check_at"] is not None

    detail = await client.get(f"/api/sources/{body['id']}")
    assert detail.json()["next_check_at"] == body["next_check_at"]
    assert detail.json()["due"] is False


async def test_manual_source_is_due_once_next_check_passes(auth_client):
    """A past ``next_check_at`` marks the source due (the override path)."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={
            "name": "Stale board",
            "url": "https://protected.example/jobs",
            "type": "manual",
            "config": {"cadence_days": 7, "next_check_at": "2020-01-01T00:00:00+00:00"},
        },
    )
    assert created.status_code == 201
    assert created.json()["due"] is True


async def test_non_manual_sources_are_never_due(auth_client):
    """The watchlist fields stay empty for scraped source types."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={"name": "Acme", "url": "https://acme.example", "type": "career_page"},
    )
    body = created.json()
    assert body["next_check_at"] is None
    assert body["due"] is False


async def test_create_manual_source_rejects_invalid_cadence(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/sources",
        json={
            "name": "Bad cadence",
            "url": "https://protected.example/jobs",
            "type": "manual",
            "config": {"cadence_days": 0},
        },
    )
    assert response.status_code == 422
    assert "cadence_days" in response.json()["detail"]


async def test_create_manual_source_rejects_cadence_above_the_max(auth_client):
    """The published bounds are enforced: 366 days is a 422, not a silent clamp."""
    client, _, _ = auth_client
    response = await client.post(
        "/api/sources",
        json={
            "name": "Forever cadence",
            "url": "https://protected.example/jobs",
            "type": "manual",
            "config": {"cadence_days": 366},
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "cadence_days" in detail
    assert "365" in detail


async def test_manual_metadata_publishes_the_cadence_contract(auth_client):
    """GET /manual-metadata is the single source of truth both UIs read."""
    client, _, _ = auth_client
    response = await client.get("/api/sources/manual-metadata")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "manual"
    assert body["cadence_days"] == {"default": 7, "min": 1, "max": 365}
    assert body["required_config"] == []
    assert set(body["optional_config"]) >= {"cadence_days", "notes"}
    assert body["example_config"]["cadence_days"] == 7


async def test_update_manual_source_keeps_the_config_the_client_sends(auth_client):
    """PUT round-trips engine-managed keys, so merging in the UI is enough.

    Both clients used to rebuild ``config`` as ``{cadence_days}`` only, which
    dropped ``next_check_at``/``reminded_at``/``notes`` and made the sweep
    re-remind an already-checked source. The API must never be the one losing
    those keys: whatever the client sends is what comes back.
    """
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={
            "name": "Watchlist",
            "url": "https://protected.example/jobs",
            "type": "manual",
            "config": {"cadence_days": 5, "next_check_at": "2030-01-01T00:00:00+00:00"},
        },
    )
    source_id = created.json()["id"]

    response = await client.put(
        f"/api/sources/{source_id}",
        json={
            "config": {
                "cadence_days": 9,
                "notes": "check the Slack #hiring channel",
                "next_check_at": "2030-01-01T00:00:00+00:00",
                "reminded_at": "2030-01-01T00:00:00+00:00",
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["config"] == {
        "cadence_days": 9,
        "notes": "check the Slack #hiring channel",
        "next_check_at": "2030-01-01T00:00:00+00:00",
        "reminded_at": "2030-01-01T00:00:00+00:00",
    }
    # An untouched source is still not due, and the reminder stays recorded.
    assert response.json()["due"] is False


async def test_check_manual_source_reschedules_it(auth_client):
    """POST /check stamps the hand-check and pushes the next reminder out."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={
            "name": "Watchlist",
            "url": "https://protected.example/jobs",
            "type": "manual",
            "config": {
                "cadence_days": 5,
                "next_check_at": "2020-01-01T00:00:00+00:00",
                "reminded_at": "2020-01-01T00:00:00+00:00",
            },
        },
    )
    assert created.json()["due"] is True
    source_id = created.json()["id"]

    checked = await client.post(f"/api/sources/{source_id}/check")

    assert checked.status_code == 200
    body = checked.json()
    assert body["due"] is False
    assert body["last_scraped"] is not None
    assert body["health"] == "healthy"
    # The reminder is cleared and a fresh due date scheduled (5 days out).
    assert "reminded_at" not in (body["config"] or {})
    assert body["next_check_at"] > "2020-01-01"


async def test_check_rejects_non_manual_sources(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={"name": "Acme", "url": "https://acme.example", "type": "career_page"},
    )
    response = await client.post(f"/api/sources/{created.json()['id']}/check")
    assert response.status_code == 400
    assert "manual" in response.json()["detail"]


async def test_check_is_user_scoped(auth_client, db_client, db_session):
    """Another user's watchlist source cannot be marked as checked."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={"name": "Mine", "url": "https://protected.example", "type": "manual"},
    )
    source_id = created.json()["id"]

    user_b = await create_user(db_session, email="checker@example.com")
    login = await db_client.post(
        "/api/auth/login", json={"email": user_b.email, "password": "password123"}
    )
    db_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    assert (await db_client.post(f"/api/sources/{source_id}/check")).status_code == 404


async def test_run_preview_explains_that_manual_sources_are_hand_checked(monkeypatch):
    """The preview never fetches a manual source — it says why instead."""

    def _never_looked_up(source, api_key=None):  # pragma: no cover - must not run
        raise AssertionError("manual sources must not reach the scraper registry")

    monkeypatch.setattr("scrapers.registry.get_scraper", _never_looked_up)

    response = await _run_preview(
        source_type=SourceType.manual, url="https://protected.example/jobs", config={}
    )

    assert response.status_code is None
    assert response.jobs_found == 0
    assert response.error is not None
    assert "manual" in response.error
    assert response.fetched_url == "https://protected.example/jobs"


# --- Avoid flag (ADR 019) -----------------------------------------------------


async def test_new_sources_are_not_avoided(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={"name": "Acme", "url": "https://acme.example", "type": "career_page"},
    )
    body = created.json()
    assert body["avoided"] is False
    assert body["avoided_at"] is None
    assert body["avoid_reason"] is None


async def test_avoid_mutes_a_due_source_without_hiding_it(auth_client):
    """An avoided source stops nagging but stays in the list with its reason."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={
            "name": "Sketchy board",
            "url": "https://sketchy.example/jobs",
            "type": "manual",
            "config": {
                "cadence_days": 7,
                "next_check_at": "2020-01-01T00:00:00+00:00",
                "reminded_at": "2020-01-01T00:00:00+00:00",
            },
        },
    )
    assert created.json()["due"] is True
    source_id = created.json()["id"]

    avoided = await client.post(
        f"/api/sources/{source_id}/avoid",
        json={"avoided": True, "reason": "  recruiter spam  "},
    )

    assert avoided.status_code == 200
    body = avoided.json()
    assert body["avoided"] is True
    assert body["avoided_at"] is not None
    # The reason is trimmed so the badge tooltip never shows stray whitespace.
    assert body["avoid_reason"] == "recruiter spam"
    # Never due again while avoided, even though next_check_at is in the past.
    assert body["due"] is False
    assert body["next_check_at"].startswith("2020-01-01")

    # Still listed — that is the whole point of the flag.
    listing = await client.get("/api/sources")
    assert [item["id"] for item in listing.json()] == [source_id]

    # Idempotent: avoiding twice keeps the original "avoided since" timestamp
    # and the reason the user already wrote.
    again = await client.post(f"/api/sources/{source_id}/avoid", json={"avoided": True})
    assert again.json()["avoided_at"] == body["avoided_at"]
    assert again.json()["avoid_reason"] == "recruiter spam"

    # An explicit empty reason clears it without un-avoiding the source.
    cleared = await client.post(
        f"/api/sources/{source_id}/avoid", json={"avoided": True, "reason": ""}
    )
    assert cleared.json()["avoided"] is True
    assert cleared.json()["avoid_reason"] is None


async def test_restore_re_arms_exactly_one_nudge(auth_client):
    """Restoring clears the flag and the stale reminder, so the sweep nudges once."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={
            "name": "Second chance",
            "url": "https://protected.example/jobs",
            "type": "manual",
            "config": {
                "cadence_days": 7,
                "next_check_at": "2020-01-01T00:00:00+00:00",
                "reminded_at": "2020-01-01T00:00:00+00:00",
                "notes": "check the Slack #hiring channel",
            },
        },
    )
    source_id = created.json()["id"]
    assert (
        await client.post(f"/api/sources/{source_id}/avoid", json={"avoided": True})
    ).status_code == 200

    restored = await client.post(f"/api/sources/{source_id}/avoid", json={"avoided": False})

    assert restored.status_code == 200
    body = restored.json()
    assert body["avoided"] is False
    assert body["avoided_at"] is None
    assert body["avoid_reason"] is None
    # Overdue again, and the stale reminder is gone → one fresh notification.
    assert body["due"] is True
    assert "reminded_at" not in (body["config"] or {})
    # The rest of the watchlist config is untouched.
    assert body["config"]["notes"] == "check the Slack #hiring channel"
    assert body["config"]["next_check_at"] == "2020-01-01T00:00:00+00:00"


async def test_avoid_applies_to_every_source_type(auth_client):
    """The flag is not manual-only: a scraped board can be avoided too."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={"name": "Noisy agg", "url": "https://agg.example", "type": "aggregator"},
    )
    source_id = created.json()["id"]

    avoided = await client.post(
        f"/api/sources/{source_id}/avoid", json={"avoided": True, "reason": "duplicates"}
    )

    assert avoided.status_code == 200
    assert avoided.json()["avoided"] is True
    assert avoided.json()["avoid_reason"] == "duplicates"
    # Non-manual sources have no due date to begin with.
    assert avoided.json()["due"] is False


async def test_update_source_can_avoid_and_restore(auth_client):
    """PUT drives the flag too, so the form needs no second call."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={"name": "Acme", "url": "https://acme.example", "type": "career_page"},
    )
    source_id = created.json()["id"]

    avoided = await client.put(
        f"/api/sources/{source_id}", json={"avoided": True, "avoid_reason": "scammy"}
    )
    assert avoided.status_code == 200
    assert avoided.json()["avoided"] is True
    assert avoided.json()["avoid_reason"] == "scammy"
    assert avoided.json()["avoided_at"] is not None

    # Editing the reason alone keeps the source avoided.
    edited = await client.put(f"/api/sources/{source_id}", json={"avoid_reason": "worse"})
    assert edited.json()["avoided"] is True
    assert edited.json()["avoid_reason"] == "worse"

    restored = await client.put(f"/api/sources/{source_id}", json={"avoided": False})
    assert restored.json()["avoided"] is False
    assert restored.json()["avoided_at"] is None
    assert restored.json()["avoid_reason"] is None


async def test_avoid_reason_is_ignored_while_active(auth_client):
    """A reason never sticks to a source the user did not flag."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={"name": "Acme", "url": "https://acme.example", "type": "career_page"},
    )
    source_id = created.json()["id"]

    updated = await client.put(f"/api/sources/{source_id}", json={"avoid_reason": "hmm"})

    assert updated.json()["avoided"] is False
    assert updated.json()["avoid_reason"] is None


async def test_avoid_reason_is_length_capped(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={"name": "Acme", "url": "https://acme.example", "type": "career_page"},
    )
    source_id = created.json()["id"]

    response = await client.post(
        f"/api/sources/{source_id}/avoid", json={"avoided": True, "reason": "x" * 281}
    )

    assert response.status_code == 422


async def test_avoid_is_user_scoped(auth_client, db_client, db_session):
    """Another user's source cannot be flagged as avoided."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={"name": "Mine", "url": "https://protected.example", "type": "manual"},
    )
    source_id = created.json()["id"]

    user_b = await create_user(db_session, email="avoider@example.com")
    login = await db_client.post(
        "/api/auth/login", json={"email": user_b.email, "password": "password123"}
    )
    db_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    response = await db_client.post(f"/api/sources/{source_id}/avoid", json={"avoided": True})
    assert response.status_code == 404
