"""Tests for the single-URL job import (ADR 025).

The service is exercised through the *real* ``CareerPageScraper`` (only the HTTP
fetch is faked), so the JSON-LD/CSS extraction and normalization the engine uses
are the ones under test. The endpoint tests stub the service: they check the
contract the dialog depends on (nothing persisted, duplicate detection, an error
travels as HTTP 200).
"""

import asyncio
from datetime import date

import httpx
import pytest
from scrapers.types import ScrapedPage
from scrapers.utils import RobotsDecision
from sqlalchemy import func, select

from app.config import settings
from app.models.job import Job
from app.services import job_import
from app.services.job_import import ImportedJob, html_to_text, import_job_from_url
from app.services.llm_config import LlmRuntimeConfig
from tests.helpers import create_user

URL = "https://acme.example/jobs/1"

JSON_LD_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "Staff Python Engineer",
  "datePosted": "2026-02-01",
  "hiringOrganization": {"@type": "Organization", "name": "Acme"},
  "jobLocation": {"@type": "Place", "address": {
    "@type": "PostalAddress", "addressLocality": "Sao Paulo", "addressCountry": "BR"}},
  "skills": ["Python", "FastAPI"],
  "description": "<p>Own the API.</p><ul><li>FastAPI</li></ul>"
}
</script>
</head><body><h1>Fallback title</h1></body></html>
"""

# No JSON-LD: the heuristic CSS selectors have to do the work, and the tags have
# to come from the taxonomy instead of the page.
CSS_HTML = """
<html><body>
  <h1>Senior Backend Engineer</h1>
  <div class="company">Acme</div>
  <div class="location">Remote, Brazil</div>
  <div class="job-description"><p>Build APIs with Python and FastAPI.</p></div>
</body></html>
"""

# What a JS-only board returns to a plain HTTP fetch.
SHELL_HTML = "<html><body><div id=\"app\"></div></body></html>"

LLM = LlmRuntimeConfig(
    enabled=True, api_key="sk-test", base_url="https://llm.example/v1", model="gpt-4o-mini"
)


def _page(html: str, url: str = URL, status_code: int = 200) -> ScrapedPage:
    return ScrapedPage(html_content=html, status_code=status_code, final_url=url)


def _serve(monkeypatch, page: ScrapedPage) -> list[str]:
    """Serve ``page`` for every fetch and record the URLs that were fetched."""
    calls: list[str] = []

    async def fake_fetch_html(url, *, auth=None, **kwargs):
        calls.append(url)
        return page

    monkeypatch.setattr("scrapers.career_page.fetch_html", fake_fetch_html)
    return calls


def _fail(monkeypatch, exc: Exception) -> None:
    async def failing_fetch(url, *, auth=None, **kwargs):
        raise exc

    monkeypatch.setattr("scrapers.career_page.fetch_html", failing_fetch)


# --- Extraction ---------------------------------------------------------------


async def test_json_ld_posting_is_extracted(monkeypatch):
    _serve(monkeypatch, _page(JSON_LD_HTML))
    draft = await import_job_from_url(URL)

    assert draft.error is None
    assert draft.extraction == "json_ld"
    assert draft.title == "Staff Python Engineer"
    assert draft.company == "Acme"
    assert draft.location.startswith("Sao Paulo")
    assert draft.posted_date == date(2026, 2, 1)
    assert draft.tags == ["Python", "FastAPI"]
    assert draft.url == URL
    # The JSON-LD description is HTML; the form needs plain text.
    assert "<p>" not in (draft.description or "")
    assert "Own the API." in draft.description
    assert "FastAPI" in draft.description


async def test_css_fallback_and_taxonomy_tags(monkeypatch):
    _serve(monkeypatch, _page(CSS_HTML))
    draft = await import_job_from_url(URL)

    assert draft.extraction == "css"
    assert draft.title == "Senior Backend Engineer"
    assert draft.company == "Acme"
    assert draft.location == "Remote, Brazil"
    # No page chips: the taxonomy fills the tags, so the filter still works.
    assert "fastapi" in draft.tags
    assert "python" in draft.tags
    assert len(draft.tags) <= 10


async def test_unknown_company_is_left_blank_for_the_user(monkeypatch):
    html = """
    <html><head><script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "JobPosting",
     "title": "Platform Engineer", "description": "Run the platform."}
    </script></head><body></body></html>
    """
    _serve(monkeypatch, _page(html))
    draft = await import_job_from_url(URL)

    # `normalize()` would store "Unknown"; the form must ask instead.
    assert draft.company == ""
    assert any("company missing" in warning for warning in draft.warnings)


async def test_js_rendered_shell_yields_an_empty_draft(monkeypatch):
    _serve(monkeypatch, _page(SHELL_HTML))
    draft = await import_job_from_url(URL)

    assert draft.title == ""
    assert draft.description is None
    assert draft.extraction in {"css", "none"}
    assert draft.warnings


def test_html_to_text_keeps_blocks_apart():
    assert html_to_text("<p>One</p><p>Two</p>") == "One\nTwo"
    assert html_to_text("   ") is None
    assert html_to_text(None) is None


# --- Failure modes (reported, never raised) -----------------------------------


async def test_timeout_is_reported(monkeypatch):
    async def slow_fetch(url, *, auth=None, **kwargs):
        await asyncio.sleep(0.5)
        return _page(JSON_LD_HTML)

    monkeypatch.setattr("scrapers.career_page.fetch_html", slow_fetch)
    monkeypatch.setattr(settings, "job_import_timeout_seconds", 0.01)

    draft = await import_job_from_url(URL)
    assert draft.error is not None
    assert "timed out" in draft.error
    assert draft.title == ""


async def test_http_error_keeps_the_status_code(monkeypatch):
    request = httpx.Request("GET", URL)
    response = httpx.Response(404, request=request)
    _fail(
        monkeypatch,
        httpx.HTTPStatusError("404 Not Found", request=request, response=response),
    )

    draft = await import_job_from_url(URL)
    assert draft.status_code == 404
    assert draft.error


async def test_blocked_url_is_reported(monkeypatch):
    """The SSRF guard's refusal has to reach the dialog, not blow up the request."""
    _fail(monkeypatch, ValueError("Blocked address 127.0.0.1 for host 'localhost'"))

    draft = await import_job_from_url(URL)
    assert draft.error is not None
    assert "Blocked address" in draft.error


async def test_robots_is_not_checked_by_default(monkeypatch):
    """A page the user is already reading is fetched like the source preview."""
    calls = _serve(monkeypatch, _page(JSON_LD_HTML))

    def boom(url):  # pragma: no cover - must not be called
        raise AssertionError("robots.txt must not be consulted by default")

    monkeypatch.setattr(job_import, "robots_decision", boom)
    draft = await import_job_from_url(URL)

    assert draft.error is None
    assert calls == [URL]


async def test_robots_disallow_skips_the_fetch(monkeypatch):
    monkeypatch.setattr(settings, "job_import_respect_robots", True)
    monkeypatch.setattr(
        job_import,
        "robots_decision",
        lambda url: RobotsDecision(
            allowed=False,
            reason="disallowed",
            robots_url="https://acme.example/robots.txt",
        ),
    )
    calls = _serve(monkeypatch, _page(JSON_LD_HTML))

    draft = await import_job_from_url(URL)
    assert draft.error == "robots.txt disallows this page"
    assert calls == []


async def test_robots_unreachable_is_a_retryable_error(monkeypatch):
    monkeypatch.setattr(settings, "job_import_respect_robots", True)
    monkeypatch.setattr(
        job_import,
        "robots_decision",
        lambda url: RobotsDecision(
            allowed=False,
            reason="unavailable",
            robots_url="https://acme.example/robots.txt",
            status_code=503,
        ),
    )
    _serve(monkeypatch, _page(JSON_LD_HTML))

    draft = await import_job_from_url(URL)
    assert draft.error is not None
    assert "unreachable" in draft.error
    assert "HTTP 503" in draft.error


# --- Optional LLM gap-fill ----------------------------------------------------

PARTIAL_HTML = """
<html><body>
  <h1>Staff Engineer</h1>
  <div class="company">Acme</div>
  <p>We are hiring.</p>
</body></html>
"""


async def test_llm_is_not_called_for_a_complete_page(monkeypatch):
    _serve(monkeypatch, _page(JSON_LD_HTML))

    def boom(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("a complete draft must not cost an LLM call")

    monkeypatch.setattr(job_import, "chat_json", boom)
    draft = await import_job_from_url(URL, llm_config=LLM)

    assert draft.llm_used is False
    assert draft.title == "Staff Python Engineer"


async def test_llm_fills_gaps_without_overwriting_the_page(monkeypatch):
    _serve(monkeypatch, _page(PARTIAL_HTML))

    async def fake_chat_json(config, **kwargs):
        return {
            "title": "Wrong title",
            "company": "Wrong company",
            "location": "Remote",
            "posted_date": "2026-02-01",
            "description": "<p>Own the API.</p>",
        }

    monkeypatch.setattr(job_import, "chat_json", fake_chat_json)
    draft = await import_job_from_url(URL, llm_config=LLM)

    assert draft.title == "Staff Engineer"  # from the page, not the model
    assert draft.company == "Acme"
    assert draft.location == "Remote"
    assert draft.posted_date == date(2026, 2, 1)
    assert draft.description == "Own the API."
    assert draft.llm_used is True
    assert any("AI" in warning for warning in draft.warnings)


async def test_llm_failure_degrades_to_the_draft(monkeypatch):
    _serve(monkeypatch, _page(PARTIAL_HTML))

    async def failing_chat_json(config, **kwargs):
        return None

    monkeypatch.setattr(job_import, "chat_json", failing_chat_json)
    draft = await import_job_from_url(URL, llm_config=LLM)

    assert draft.error is None
    assert draft.title == "Staff Engineer"
    assert draft.company == "Acme"
    assert draft.llm_used is False
    assert any("unavailable" in warning for warning in draft.warnings)


async def test_disabled_llm_is_never_called(monkeypatch):
    _serve(monkeypatch, _page(PARTIAL_HTML))

    def boom(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("a disabled LLM must not be called")

    monkeypatch.setattr(job_import, "chat_json", boom)
    off = LlmRuntimeConfig(enabled=False, api_key="", base_url="https://x/v1", model="m")
    draft = await import_job_from_url(URL, llm_config=off)

    assert draft.llm_used is False


# --- Endpoint: POST /api/jobs/import-preview ----------------------------------


def _draft(**overrides) -> ImportedJob:
    draft = ImportedJob(
        fetched_url=URL,
        status_code=200,
        url=URL,
        title="Staff Engineer",
        company="Acme",
        description="Own the API.",
        tags=["python"],
        extraction="json_ld",
    )
    for key, value in overrides.items():
        setattr(draft, key, value)
    return draft


@pytest.fixture
def stub_import(monkeypatch):
    """Replace the scraper round-trip; the endpoint keeps doing its own work."""

    def install(draft: ImportedJob):
        async def fake_import(url, *, llm_config=None):
            fake_import.url = url
            return draft

        fake_import.url = None
        monkeypatch.setattr("app.routers.jobs.import_job_from_url", fake_import)
        return fake_import

    return install


async def test_import_preview_returns_a_draft_and_saves_nothing(
    auth_client, db_session, stub_import
):
    client, _, _ = auth_client
    stub = stub_import(_draft())

    response = await client.post("/api/jobs/import-preview", json={"url": f"  {URL}  "})

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Staff Engineer"
    assert body["company"] == "Acme"
    assert body["tags"] == ["python"]
    assert body["extraction"] == "json_ld"
    assert body["llm_used"] is False
    assert body["existing_job_id"] is None
    assert body["error"] is None
    assert stub.url == URL  # the pasted value is trimmed before fetching
    # Preview only: the form's Save is what persists.
    assert await db_session.scalar(select(func.count(Job.id))) == 0


async def test_import_preview_flags_an_already_saved_job(auth_client, stub_import):
    client, _, _ = auth_client
    created = await client.post(
        "/api/jobs", json={"title": "Staff Engineer", "company": "Acme", "url": URL}
    )
    assert created.status_code == 201
    stub_import(_draft())

    response = await client.post("/api/jobs/import-preview", json={"url": URL})

    # A duplicate is a warning, not a block: the draft is still usable.
    assert response.status_code == 200
    body = response.json()
    assert body["existing_job_id"] == created.json()["id"]
    assert body["title"] == "Staff Engineer"


async def test_import_preview_matches_the_url_the_page_reported(
    auth_client, stub_import
):
    """Redirects and canonical URLs still line up with a saved job."""
    client, _, _ = auth_client
    canonical = "https://acme.example/jobs/staff-engineer"
    created = await client.post(
        "/api/jobs", json={"title": "Staff Engineer", "company": "Acme", "url": canonical}
    )
    stub_import(_draft(url=canonical))

    response = await client.post("/api/jobs/import-preview", json={"url": URL})

    assert response.json()["existing_job_id"] == created.json()["id"]


async def test_import_preview_ignores_another_users_job(
    auth_client, db_session, stub_import
):
    client, _, _ = auth_client
    other = await create_user(db_session, email="importer-other@example.com")
    db_session.add(Job(user_id=other.id, title="Staff Engineer", company="Acme", url=URL, tags=[]))
    await db_session.commit()
    stub_import(_draft())

    response = await client.post("/api/jobs/import-preview", json={"url": URL})

    assert response.status_code == 200
    assert response.json()["existing_job_id"] is None


async def test_import_preview_reports_a_fetch_error_with_http_200(
    auth_client, stub_import
):
    client, _, _ = auth_client
    stub_import(
        _draft(
            status_code=None,
            url=None,
            title="",
            company="",
            description=None,
            tags=[],
            extraction="none",
            error="timed out after 15s — the site may be slow or JS-rendered",
            warnings=["the page has no readable job description"],
        )
    )

    response = await client.post("/api/jobs/import-preview", json={"url": URL})

    # The dialog shows the reason next to the fields; it is not an API failure.
    assert response.status_code == 200
    body = response.json()
    assert body["error"].startswith("timed out")
    assert body["title"] == ""
    assert body["warnings"]


async def test_import_preview_requires_auth(client):
    response = await client.post("/api/jobs/import-preview", json={"url": URL})
    assert response.status_code == 401


async def test_import_preview_rejects_an_empty_url(auth_client, stub_import):
    client, _, _ = auth_client
    stub = stub_import(_draft())

    response = await client.post("/api/jobs/import-preview", json={"url": ""})

    assert response.status_code == 422
    assert stub.url is None  # nothing was fetched
