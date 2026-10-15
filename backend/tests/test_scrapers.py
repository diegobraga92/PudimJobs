"""Unit tests for the scraper implementations (no DB/network required)."""

import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
import scrapers.utils as utils
from scrapers.aggregator import (
    EmbeddedJsonListScraper,
    GenericHtmlListScraper,
    get_aggregator_adapter,
)
from scrapers.career_page import CareerPageScraper
from scrapers.discovery import (
    AdzunaProvider,
    BrightDataProvider,
    DiscoveryScraper,
    GoogleCseProvider,
    GreenhouseProvider,
    JoobleProvider,
    JSearchProvider,
    JsonListProvider,
    PersonioProvider,
    RecruiteeProvider,
    SerpApiProvider,
    SmartRecruitersProvider,
    WorkdayProvider,
    get_discovery_provider,
)
from scrapers.registry import get_scraper
from scrapers.rss import RSSScraper
from scrapers.types import FetchAuth, RawJob, ScrapedPage
from scrapers.utils import (
    coerce_date,
    fetch_html,
    parse_html_list,
    parse_json_ld_jobs,
    redact_sensitive,
    relative_age,
    resolve_path,
)

from app.models.enums import SourceType

CAREER_PAGE_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "JobPosting",
  "title": "Senior Python Engineer",
  "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
  "datePosted": "2026-08-01",
  "url": "https://acme.example/jobs/42",
  "description": "Build APIs with FastAPI.",
  "skills": ["python", "fastapi"]
}
</script>
<script type="application/ld+json">
[{
  "@type": "JobPosting",
  "title": "DevOps Engineer",
  "hiringOrganization": {"name": "Acme Corp"},
  "url": "https://acme.example/jobs/43"
}]
</script>
</head></html>
"""

RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Acme Careers Feed</title>
    <link>https://acme.example/feed</link>
    <item>
      <title>Product Manager</title>
      <link>https://acme.example/jobs/100</link>
      <pubDate>Fri, 01 Aug 2026 10:00:00 GMT</pubDate>
      <description>Own the roadmap.</description>
      <guid>acme-100</guid>
    </item>
    <item>
      <title>Designer</title>
      <link>https://acme.example/jobs/101</link>
    </item>
  </channel>
</rss>
"""

AGGREGATOR_HTML = """
<html><body>
<ul>
  <li class="job">
    <h2><a href="/jobs/1">Backend Engineer</a></h2>
    <span class="company">Acme</span>
    <span class="location">Remote</span>
  </li>
  <li class="job">
    <h2><a href="/jobs/2">Data Scientist</a></h2>
    <span class="company">Beta</span>
  </li>
</ul>
<a class="next" href="/jobs?page=2">Next</a>
</body></html>
"""


def _page(html: str) -> ScrapedPage:
    return ScrapedPage(html_content=html, status_code=200, final_url="https://acme.example")


def test_career_page_parses_json_ld_jobpostings():
    scraper = CareerPageScraper()
    raw = scraper.parse(_page(CAREER_PAGE_HTML))

    assert len(raw) == 2
    first = raw[0]
    assert first.title == "Senior Python Engineer"
    assert first.company == "Acme Corp"
    assert first.url == "https://acme.example/jobs/42"
    assert str(first.posted_date) == "2026-08-01"
    assert first.tags == ["python", "fastapi"]
    assert first.description == "Build APIs with FastAPI."


def test_career_page_normalize_skips_invalid():
    scraper = CareerPageScraper()
    raw = scraper.parse(_page(CAREER_PAGE_HTML))
    normalized = scraper.normalize(raw)

    assert all(item["title"] and item["url"] for item in normalized)
    assert normalized[0]["company"] == "Acme Corp"


def test_career_page_empty_page_returns_no_jobs():
    scraper = CareerPageScraper()
    raw = scraper.parse(_page("<html><body><h1>No jobs here</h1></body></html>"))
    assert raw == []


def test_rss_parses_feed_entries():
    scraper = RSSScraper()
    raw = scraper.parse(_page(RSS_FEED))

    assert len(raw) == 2
    assert raw[0].title == "Product Manager"
    assert raw[0].company == "Acme Careers Feed"
    assert raw[0].url == "https://acme.example/jobs/100"
    assert raw[0].external_id == "acme-100"


def test_aggregator_generic_html_list_parses():
    scraper = GenericHtmlListScraper(
        {
            "adapter": "generic_html_list",
            "item_selector": "li.job",
            "title_selector": "h2",
            "url_selector": "a",
            "company_selector": ".company",
            "location_selector": ".location",
            "next_page_selector": "a.next",
        }
    )
    page = ScrapedPage(
        html_content=AGGREGATOR_HTML, status_code=200, final_url="https://board.example/jobs"
    )
    raw = scraper.parse(page)
    assert len(raw) == 2
    assert raw[0].title == "Backend Engineer"
    assert raw[0].company == "Acme"
    assert raw[0].url == "https://board.example/jobs/1"
    assert raw[0].description == "Location: Remote"
    assert raw[1].title == "Data Scientist"
    assert raw[1].url == "https://board.example/jobs/2"
    assert raw[1].description is None


def test_aggregator_next_page_url():
    scraper = GenericHtmlListScraper({"next_page_selector": "a.next"})
    page = ScrapedPage(
        html_content=AGGREGATOR_HTML, status_code=200, final_url="https://board.example/jobs"
    )
    assert scraper.next_page_url(page) == "https://board.example/jobs?page=2"


def test_aggregator_next_page_url_none_without_selector():
    scraper = GenericHtmlListScraper({})
    page = ScrapedPage(
        html_content=AGGREGATOR_HTML, status_code=200, final_url="https://board.example/jobs"
    )
    assert scraper.next_page_url(page) is None


def test_aggregator_builds_next_page_from_tpl():
    """A board that pages by query string and renders no anchor uses ``next_page_tpl``."""
    scraper = GenericHtmlListScraper(
        {
            "item_selector": "li.job",
            "modality": "remote",
            "next_page_tpl": "https://board.example/pt/vagas?workModality={modality}&page={page}",
            "max_pages": 3,
        }
    )
    page = _aggregator_page(AGGREGATOR_HTML, "https://board.example/pt/vagas?workModality=remote")
    assert (
        scraper.next_page_url(page)
        == "https://board.example/pt/vagas?workModality=remote&page=2"
    )
    assert (
        scraper.next_page_url(page)
        == "https://board.example/pt/vagas?workModality=remote&page=3"
    )
    assert scraper.next_page_url(page) is None


def test_aggregator_next_page_selector_wins_over_tpl():
    """A rendered `?page=2` link is more trustworthy than a built URL, and it ends the walk."""
    scraper = GenericHtmlListScraper(
        {
            "next_page_selector": "a.next",
            "next_page_tpl": "https://board.example/jobs?page={page}",
            "max_pages": 3,
        }
    )
    assert (
        scraper.next_page_url(_aggregator_page(AGGREGATOR_HTML))
        == "https://board.example/jobs?page=2"
    )


def test_aggregator_next_page_tpl_without_max_pages_is_inert():
    """The template alone must not paginate: `max_pages` gates the walk."""
    scraper = GenericHtmlListScraper(
        {"next_page_tpl": "https://board.example/jobs?page={page}"}
    )
    assert scraper.next_page_url(_aggregator_page(AGGREGATOR_HTML)) is None


def test_aggregator_relative_next_page_tpl_resolves_against_the_page():
    """A host-agnostic template (`?pagina={page}`) is joined to the page it was read from."""
    scraper = GenericHtmlListScraper({"next_page_tpl": "?pagina={page}", "max_pages": 2})
    page = _aggregator_page(AGGREGATOR_HTML, "https://www.nerdin.com.br/vagas.php")
    assert scraper.next_page_url(page) == "https://www.nerdin.com.br/vagas.php?pagina=2"


def test_aggregator_reports_a_bad_next_page_tpl():
    scraper = GenericHtmlListScraper(
        {"next_page_tpl": "https://board.example/jobs?page={missing}", "max_pages": 2}
    )
    with pytest.raises(ValueError, match="next_page_tpl"):
        scraper.next_page_url(_aggregator_page(AGGREGATOR_HTML))


def test_aggregator_url_tpl_builds_the_first_fetch():
    """A term kept in the config replaces the stored URL on page 1 (and in `next_page_tpl`)."""
    scraper = GenericHtmlListScraper(
        {
            "term": "rust",
            "url_tpl": "https://www.trabalhabrasil.com.br/vagas-de-emprego/{term}",
            "next_page_tpl": "https://www.trabalhabrasil.com.br/vagas-de-emprego/{term}?pagina={page}",
            "max_pages": 2,
        }
    )
    assert scraper.first_fetch_url("https://www.trabalhabrasil.com.br/vagas-de-emprego/") == (
        "https://www.trabalhabrasil.com.br/vagas-de-emprego/rust"
    )
    assert scraper.next_page_url(
        _aggregator_page(
            AGGREGATOR_HTML, "https://www.trabalhabrasil.com.br/vagas-de-emprego/rust"
        )
    ) == "https://www.trabalhabrasil.com.br/vagas-de-emprego/rust?pagina=2"


def test_aggregator_without_url_tpl_fetches_the_stored_url_verbatim():
    """Arguments already in the stored URL are the simplest filter: no config needed."""
    scraper = GenericHtmlListScraper({"item_selector": "div.js_cardLink"})
    url = "https://www.infojobs.com.br/empregos.aspx?palabra=Rust"
    assert scraper.first_fetch_url(url) == url


def test_aggregator_reports_a_bad_url_tpl():
    scraper = GenericHtmlListScraper({"url_tpl": "https://board.example/{term}"})
    with pytest.raises(ValueError, match="url_tpl"):
        scraper.first_fetch_url("https://board.example/jobs")


def test_aggregator_metadata_publishes_the_url_and_pagination_templates():
    optional = GenericHtmlListScraper.config_metadata()["optional"]
    assert {"url_tpl", "next_page_tpl", "next_page_selector"} <= set(optional)


def test_aggregator_parses_rows_that_are_the_link():
    """dev.pro-style rows (`a.position-row`) carry no inner anchor to read the href from."""
    html = """
    <div class="position-wrapper">
      <a class="position-row" href="https://career.dev.pro/vacancy/5cfad0/">
        <div class="position-title"><h3>Senior System Analyst</h3></div>
        <div class="position-info"><span> Latin America, Remote </span></div>
      </a>
    </div>
    <div class="vacancy_pagination">
      <a class="page-numbers" href="https://career.dev.pro/open-positions/page/2/">2</a>
    </div>
    """
    page = _aggregator_page(html, "https://career.dev.pro/open-positions/")
    scraper = GenericHtmlListScraper(
        {
            "item_selector": "a.position-row",
            "title_selector": "h3",
            "location_selector": ".position-info span",
            "next_page_selector": ".vacancy_pagination a.page-numbers",
            "max_pages": 2,
        }
    )
    raw = scraper.parse(page)
    assert [job.title for job in raw] == ["Senior System Analyst"]
    assert raw[0].url == "https://career.dev.pro/vacancy/5cfad0/"
    assert raw[0].description == "Location: Latin America, Remote"
    assert scraper.next_page_url(page) == "https://career.dev.pro/open-positions/page/2/"

    detail = GenericHtmlListScraper(
        {"detail": True, "item_selector": "a.position-row", "url_selector": "a"}
    )
    assert detail.discover_urls(page) == ["https://career.dev.pro/vacancy/5cfad0/"]


def test_aggregator_normalize_skips_invalid():
    scraper = GenericHtmlListScraper({})
    normalized = scraper.normalize(
        [RawJob(title="X", company="Y", url="https://x.example/job", external_id="job-1")]
    )
    assert normalized[0]["company"] == "Y"
    assert normalized[0]["external_id"] == "job-1"
    assert scraper.normalize([RawJob(title="", company="", url="")]) == []
    # Whitespace-only titles are dropped, not stored as empty strings.
    assert scraper.normalize([RawJob(title="   ", company="Y", url="https://x.example/job")]) == []


DETAIL_LIST_HTML = """
<html><body>
<ul>
  <li class="job">
    <a href="/jobs/1">Backend Engineer</a><time datetime="2026-08-01">Aug 1</time>
  </li>
  <li class="job"><a href="/jobs/2"></a></li>
</ul>
</body></html>
"""

DETAIL_PAGE_HTML = """
<html><body>
<h1 class="job-title">Staff Platform Engineer</h1>
<div class="company">Acme</div>
<div class="job-description">Own the platform.</div>
<div class="job-location">Remote, Brazil</div>
<time class="date" datetime="2026-08-02">2026-08-02</time>
</body></html>
"""


def _aggregator_page(html: str, url: str = "https://board.example/jobs") -> ScrapedPage:
    return ScrapedPage(html_content=html, status_code=200, final_url=url)


def test_aggregator_list_mode_parses_dates():
    """The documented `date_selector` is honoured (reads `datetime` attrs too)."""
    scraper = GenericHtmlListScraper(
        {
            "item_selector": "li.job",
            "title_selector": "a",
            "url_selector": "a",
            "date_selector": "time",
        }
    )
    raw = scraper.parse(_aggregator_page(DETAIL_LIST_HTML))
    assert [job.title for job in raw] == ["Backend Engineer"]
    assert raw[0].posted_date == date(2026, 8, 1)


def test_aggregator_detail_mode_discovers_link_only_rows():
    scraper = GenericHtmlListScraper(
        {"detail": True, "item_selector": "li.job", "url_selector": "a"}
    )
    assert scraper.discover_urls(_aggregator_page(DETAIL_LIST_HTML)) == [
        "https://board.example/jobs/1",
        "https://board.example/jobs/2",
    ]
    # Without the flag the hook is inert, so list parsing stays single-stage.
    assert GenericHtmlListScraper({}).discover_urls(_aggregator_page(DETAIL_LIST_HTML)) == []


def test_aggregator_detail_mode_parses_detail_page():
    scraper = GenericHtmlListScraper(
        {
            "detail": True,
            "company": "Acme",
            "detail_title_selector": "h1.job-title",
            "detail_company_selector": ".company",
            "detail_description_selector": ".job-description",
            "detail_location_selector": ".job-location",
            "detail_date_selector": "time.date",
        }
    )
    raw = scraper.parse(_aggregator_page(DETAIL_PAGE_HTML, "https://board.example/jobs/1"))
    assert len(raw) == 1
    assert raw[0].title == "Staff Platform Engineer"
    assert raw[0].company == "Acme"
    assert raw[0].url == "https://board.example/jobs/1"
    assert raw[0].posted_date == date(2026, 8, 2)
    assert raw[0].description is not None
    assert "Own the platform." in raw[0].description
    assert "Remote, Brazil" in raw[0].description


def test_aggregator_detail_mode_prefers_json_ld():
    scraper = GenericHtmlListScraper({"detail": True})
    raw = scraper.parse(_aggregator_page(CAREER_PAGE_HTML))
    assert [job.title for job in raw] == ["Senior Python Engineer", "DevOps Engineer"]


def test_aggregator_detail_mode_uses_config_company_when_page_has_none():
    scraper = GenericHtmlListScraper(
        {
            "detail": True,
            "company": "Acme",
            "detail_title_selector": "h1.job-title",
            "detail_description_selector": ".job-description",
        }
    )
    html = (
        "<html><body><h1 class='job-title'>Solo Role</h1>"
        "<div class='job-description'>Do it.</div></body></html>"
    )
    raw = scraper.parse(_aggregator_page(html, "https://board.example/jobs/9"))
    assert [job.title for job in raw] == ["Solo Role"]
    assert raw[0].company == "Acme"
    assert raw[0].url == "https://board.example/jobs/9"


NEXT_DATA_HTML = """
<html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props": {"pageProps": {"jobs": [
  {"id": "n-1", "title": "Next.js Engineer", "slug": "nextjs-engineer",
   "company": {"name": "Acme"}, "location": {"city": "Remote"},
   "publishedAt": "2026-08-03T09:00:00Z", "tags": ["javascript"]},
  {"id": "n-2", "title": "Nuxt Engineer", "slug": "nuxt-engineer"}
]}}}
</script>
</body></html>
"""

NUXT_HTML = """
<html><body>
<script>window.__NUXT__ = {"data": [{"jobs": [{"id": 7, "title": "Vue Engineer",
  "slug": "vue"}]}]};</script>
<script>var other = {"ignored": true};</script>
</body></html>
"""


def test_embedded_json_adapter_parses_next_data():
    scraper = EmbeddedJsonListScraper(
        {
            "adapter": "embedded_json_list",
            "payload_script": "__NEXT_DATA__",
            "items_path": "props.pageProps.jobs",
            "id_path": "id",
            "title_path": "title",
            "url_path": "slug",
            "url_tpl": "https://board.example/jobs/{url}",
            "company_path": "company.name",
            "location_path": "location.city",
            "date_path": "publishedAt",
            "tags_path": "tags",
        }
    )
    raw = scraper.parse(_aggregator_page(NEXT_DATA_HTML))

    assert [job.title for job in raw] == ["Next.js Engineer", "Nuxt Engineer"]
    first = raw[0]
    assert first.company == "Acme"
    assert first.url == "https://board.example/jobs/nextjs-engineer"
    assert first.posted_date == date(2026, 8, 3)
    assert first.tags == ["javascript", "Remote"]
    assert first.external_id == "n-1"
    # The second item has no company block, so only its slug is rendered.
    assert raw[1].url == "https://board.example/jobs/nuxt-engineer"
    assert raw[1].company == ""


def test_embedded_json_adapter_reads_a_nuxt_global():
    """The blob is decoded even with other scripts after it on the page."""
    scraper = EmbeddedJsonListScraper(
        {
            "payload_global": "__NUXT__",
            "items_path": "data[0].jobs",
            "title_path": "title",
            "url_path": "slug",
            "company": "Acme",
        }
    )
    raw = scraper.parse(_aggregator_page(NUXT_HTML))
    assert [job.title for job in raw] == ["Vue Engineer"]
    # A bare slug resolves against the page directory (urljoin semantics).
    assert raw[0].url == "https://board.example/vue"
    assert raw[0].company == "Acme"


def test_embedded_json_adapter_falls_back_to_json_ld():
    scraper = EmbeddedJsonListScraper({"items_path": "props.pageProps.jobs"})
    raw = scraper.parse(_aggregator_page(CAREER_PAGE_HTML))
    assert [job.title for job in raw] == ["Senior Python Engineer", "DevOps Engineer"]


def test_embedded_json_adapter_reports_a_non_array_items_path():
    scraper = EmbeddedJsonListScraper({"items_path": "props.pageProps.jobs.0.title"})
    with pytest.raises(ValueError, match="items_path"):
        scraper.parse(_aggregator_page(NEXT_DATA_HTML))


def test_embedded_json_adapter_is_registered():
    adapter = get_aggregator_adapter("embedded_json_list", {"items_path": "jobs"})
    assert isinstance(adapter, EmbeddedJsonListScraper)


def test_embedded_json_adapter_paginates_with_next_page_tpl():
    """`{page}` starts at 2 (page 1 is the source URL) and stops at `max_pages`."""
    scraper = EmbeddedJsonListScraper(
        {
            "items_path": "props.pageProps.jobs",
            "next_page_tpl": "https://board.example/jobs?page={page}",
            "max_pages": 3,
        }
    )
    page = _aggregator_page(NEXT_DATA_HTML)
    assert scraper.next_page_url(page) == "https://board.example/jobs?page=2"
    assert scraper.next_page_url(page) == "https://board.example/jobs?page=3"
    assert scraper.next_page_url(page) is None


def test_embedded_json_adapter_next_page_tpl_can_use_config_keys():
    """Gupy-style templates carry the search term as well as the page number."""
    scraper = EmbeddedJsonListScraper(
        {
            "items_path": "props.pageProps.initialJobList.data",
            "term": "python",
            "next_page_tpl": "https://board.example/search?term={term}&page={page}",
            "max_pages": 2,
        }
    )
    page = _aggregator_page(NEXT_DATA_HTML)
    assert (
        scraper.next_page_url(page)
        == "https://board.example/search?term=python&page=2"
    )
    assert scraper.next_page_url(page) is None


def test_embedded_json_adapter_next_page_tpl_without_max_pages_is_inert():
    """A template alone must not paginate: the worker's `max_pages` gates it."""
    scraper = EmbeddedJsonListScraper(
        {
            "items_path": "props.pageProps.jobs",
            "next_page_tpl": "https://board.example/jobs?page={page}",
        }
    )
    assert scraper.next_page_url(_aggregator_page(NEXT_DATA_HTML)) is None


def test_embedded_json_adapter_reports_a_bad_next_page_tpl():
    scraper = EmbeddedJsonListScraper(
        {
            "items_path": "props.pageProps.jobs",
            "next_page_tpl": "https://board.example/jobs?page={missing}",
            "max_pages": 2,
        }
    )
    with pytest.raises(ValueError, match="next_page_tpl"):
        scraper.next_page_url(_aggregator_page(NEXT_DATA_HTML))


class _FakeRobotsResponse:
    def __init__(self, text: str):
        self.status_code = 200
        self.text = text


def test_robots_respects_allow_and_disallow(monkeypatch):
    """robots.txt handling honours ``Allow`` (which overrides ``Disallow``)."""
    # `urllib.robotparser` returns the *first* matching rule, so Allow precedes
    # Disallow in the file (as most crawlers expect).
    monkeypatch.setattr(
        utils.httpx,
        "get",
        lambda *a, **k: _FakeRobotsResponse(
            "User-agent: *\nAllow: /private/open\nDisallow: /private\n"
        ),
    )
    utils._robots_parser_cache.clear()

    assert utils.is_allowed_by_robots("https://example.com/jobs/1") is True
    assert utils.is_allowed_by_robots("https://example.com/private/jobs/2") is False
    assert utils.is_allowed_by_robots("https://example.com/private/open/3") is True


def test_redact_sensitive_hides_query_keys():
    assert (
        redact_sensitive("https://serpapi.com/search?engine=linkedin&api_key=SECRET")
        == "https://serpapi.com/search?engine=linkedin&api_key=REDACTED"
    )
    # Keys embedded in httpx error messages are redacted too.
    msg = "Client error '403' for url 'https://serpapi.com/search?api_key=SECRET&engine=linkedin'"
    assert "SECRET" not in redact_sensitive(msg)


def test_json_ld_identifier_dict_is_coerced():
    html = """
    <script type="application/ld+json">
    {"@type": "JobPosting", "title": "T", "hiringOrganization": {"name": "C"},
     "url": "https://x.example/1",
     "identifier": {"@type": "PropertyValue", "value": "req-42"}}
    </script>
    """
    jobs = parse_json_ld_jobs(html)
    assert jobs[0].external_id == "req-42"


def test_get_aggregator_adapter_unknown_raises():
    with pytest.raises(ValueError):
        get_aggregator_adapter("does_not_exist")


def test_resolve_path_handles_dicts_indices_and_misses():
    payload = {"a": {"b": [{"c": 1}, {"c": 2}]}, "list": ["x"]}
    assert resolve_path(payload, "a.b[1].c") == 2
    assert resolve_path(payload, "a.b.0.c") == 1
    assert resolve_path(payload, "list[-1]") == "x"
    assert resolve_path(payload, "") is payload
    assert resolve_path(payload, None) is payload
    # Misses never raise; they return the default (None unless overridden).
    assert resolve_path(payload, "a.missing.c") is None
    assert resolve_path(payload, "a.b[9]") is None
    assert resolve_path(payload, "a.b.c") is None
    assert resolve_path(payload, "a", default="fallback") == {"b": [{"c": 1}, {"c": 2}]}
    assert resolve_path(payload, "nope", default="fallback") == "fallback"
    assert resolve_path(payload, {"not": "a path"}) is None


def test_coerce_date_handles_iso_epoch_and_invalid_values():
    assert coerce_date("2026-08-01T10:00:00Z") == date(2026, 8, 1)
    assert coerce_date("2026-08-01") == date(2026, 8, 1)
    assert coerce_date(date(2026, 8, 2)) == date(2026, 8, 2)
    assert coerce_date(datetime(2026, 8, 3, 5, 30)) == date(2026, 8, 3)
    assert coerce_date(1754042400) == date(2025, 8, 1)
    assert coerce_date("not a date") is None
    assert coerce_date(None) is None
    assert coerce_date(True) is None


# --- Discovery providers -------------------------------------------------------


GREENHOUSE_PAYLOAD = {
    "jobs": [
        {
            "id": 1,
            "title": "Backend Engineer",
            "location": {"name": "Remote, Brazil"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
            "updated_at": "2026-08-01T10:00:00Z",
            "content": "<p>Build APIs with Python.</p>",
        }
    ]
}

DETAIL_HTML = """
<html><body>
<h1>Senior Python Engineer</h1>
<span class="company">Acme Corp</span>
<div class="description">Build APIs.</div>
</body></html>
"""


def _json_page(payload: dict) -> ScrapedPage:
    return ScrapedPage(
        html_content=json.dumps(payload),
        status_code=200,
        final_url="https://api.example",
    )


def test_greenhouse_provider_parses_jobs():
    provider = GreenhouseProvider({"board_token": "acme", "company": "Acme"})
    assert provider.results_url() == "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
    jobs = provider.parse(_json_page(GREENHOUSE_PAYLOAD))
    assert len(jobs) == 1
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].url == "https://boards.greenhouse.io/acme/jobs/1"
    assert jobs[0].company == "Acme"
    assert "Build APIs" in jobs[0].description


def test_ats_provider_missing_config_raises():
    with pytest.raises(ValueError):
        GreenhouseProvider({}).results_url()


JSON_LIST_PAYLOAD = {
    "meta": {"total": 3},
    "data": {
        "items": [
            {
                "id": 101,
                "position": "Backend Engineer",
                "company": "Acme",
                "location": "Remote, Brazil",
                "url": "https://acme.example/jobs/101",
                "date": "2026-08-01T10:00:00",
                "tags": ["python", "fastapi"],
                "description": "<p>Build <b>APIs</b> with Python.</p>",
            },
            {
                "id": 102,
                "position": "Platform Engineer",
                "company": "Beta",
                "url": "/jobs/102",
                "date": 1754042400,
            },
            {"id": 103, "url": "https://gamma.example/jobs/103"},
        ]
    },
}

JSON_LIST_CONFIG = {
    "provider": "json_list",
    "url_tpl": "https://api.example/jobs?tag={tag}",
    "tag": "python",
    "items_path": "data.items",
    "id_path": "id",
    "title_path": "position",
    "url_path": "url",
    "company_path": "company",
    "location_path": "location",
    "date_path": "date",
    "tags_path": "tags",
    "description_path": "description",
}


def test_json_list_provider_parses_nested_items():
    provider = JsonListProvider(JSON_LIST_CONFIG)
    assert provider.results_url() == "https://api.example/jobs?tag=python"
    assert provider.family == "json"

    jobs = provider.parse(_json_page(JSON_LIST_PAYLOAD))

    # The third item has no title, so it is skipped.
    assert [job.title for job in jobs] == ["Backend Engineer", "Platform Engineer"]
    first = jobs[0]
    assert first.company == "Acme"
    assert first.external_id == "101"
    assert first.posted_date == date(2026, 8, 1)
    assert first.tags == ["python", "fastapi", "Remote, Brazil"]
    assert first.description is not None
    assert "Build APIs" in first.description
    assert "<b>" not in first.description
    # Relative URLs resolve against the fetched page; epoch dates are converted.
    assert jobs[1].url == "https://api.example/jobs/102"
    assert jobs[1].posted_date == date(2025, 8, 1)
    assert jobs[1].tags == []


def test_json_list_provider_root_array_and_plain_url():
    provider = JsonListProvider(
        {
            "provider": "json_list",
            "url": "https://api.example/list",
            "title_path": "name",
            "url_path": "link",
        }
    )
    assert provider.results_url() == "https://api.example/list"
    page = ScrapedPage(
        html_content=json.dumps([{"name": "SRE", "link": "https://x.example/1"}]),
        status_code=200,
        final_url="https://api.example/list",
    )
    jobs = provider.parse(page)
    assert [job.title for job in jobs] == ["SRE"]
    assert jobs[0].company == ""
    assert jobs[0].posted_date is None


def test_json_list_provider_company_fallback_and_max_results():
    provider = JsonListProvider(
        {
            "url": "https://api.example/list",
            "items_path": "jobs",
            "title_path": "name",
            "url_path": "link",
            "company": "Acme Board",
            "max_results": 1,
        }
    )
    page = ScrapedPage(
        html_content=json.dumps(
            {
                "jobs": [
                    {"name": "A", "link": "https://x.example/1"},
                    {"name": "B", "link": "https://x.example/2"},
                ]
            }
        ),
        status_code=200,
        final_url="https://api.example/list",
    )
    jobs = provider.parse(page)
    assert len(jobs) == 1
    assert jobs[0].company == "Acme Board"


def test_json_list_provider_accepts_a_single_object_payload():
    provider = JsonListProvider(
        {
            "url": "https://api.example/one",
            "items_path": "job",
            "title_path": "name",
            "url_path": "link",
        }
    )
    page = ScrapedPage(
        html_content=json.dumps({"job": {"name": "Solo", "link": "https://x.example/1"}}),
        status_code=200,
        final_url="https://api.example/one",
    )
    assert [job.title for job in provider.parse(page)] == ["Solo"]


def test_json_list_provider_errors_are_explicit():
    with pytest.raises(ValueError, match="url"):
        JsonListProvider({"provider": "json_list"}).results_url()
    with pytest.raises(ValueError, match="missing"):
        JsonListProvider({"url_tpl": "https://api.example?tag={missing}"}).results_url()
    provider = JsonListProvider({"url": "https://api.example", "items_path": "items"})
    with pytest.raises(ValueError, match="items_path"):
        provider.parse(_json_page({"items": "nope"}))
    with pytest.raises(ValueError, match="valid JSON"):
        provider.parse(
            ScrapedPage(
                html_content="<html></html>",
                status_code=200,
                final_url="https://api.example",
            )
        )


def test_json_list_provider_is_registered_and_dispatched():
    provider = get_discovery_provider("json_list", {"url": "https://api.example/list"})
    assert isinstance(provider, JsonListProvider)
    scraper = get_scraper(
        SimpleNamespace(
            type=SourceType.discovery,
            config={"provider": "json_list", "url": "https://api.example/list"},
        )
    )
    assert scraper.first_fetch_url("https://ignored.example") == ("https://api.example/list")

# --- Keyed JSON APIs (json_list auth/POST/paging, Adzuna, Jooble, JSearch) -----


def test_json_list_places_the_key_where_the_config_says():
    """`auth` covers query strings, headers and template embedding."""
    provider = JsonListProvider(
        {"url": "https://api.example/jobs?tag=python", "auth": {"in": "query", "name": "api_key"}},
        api_key="SECRET",
    )
    assert provider.results_url() == "https://api.example/jobs?tag=python&api_key=SECRET"
    # No existing query string: the key still lands on a `?`.
    bare = JsonListProvider({"url": "https://api.example/jobs", "auth": "query"}, api_key="SECRET")
    assert bare.results_url().endswith("?X-API-Key=SECRET")
    # An absent `auth` leaves the key to the URL template.
    embedded = JsonListProvider({"url": "https://api.example/jobs?key={api_key}"}, api_key="SECRET")
    assert embedded.results_url() == "https://api.example/jobs?key=SECRET"


def test_json_list_rejects_an_unknown_auth_location():
    provider = JsonListProvider({"url": "https://api.example/jobs", "auth": {"in": "cookie"}})
    with pytest.raises(ValueError, match="must be one of"):
        provider.results_url()


def test_json_list_needs_a_key_when_the_template_uses_it():
    provider = JsonListProvider({"url": "https://api.example/{api_key}/jobs"})
    with pytest.raises(ValueError, match="API key"):
        provider.results_url()


async def test_json_list_sends_header_keys_and_posts_rendered_bodies(
    monkeypatch, offline_fetch
):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"jobs": []})

    _patch_httpx_transport(monkeypatch, handler)
    provider = JsonListProvider(
        {
            "url": "https://api.example/{api_key}/search",
            "auth": {"in": "header", "name": "X-Api-Key"},
            "method": "POST",
            "body": {"q": "{query}", "page": "{page}"},
            "query": "python",
        },
        api_key="SUPER-SECRET",
    )
    page = await provider.fetch(provider.results_url())

    request = seen[0]
    assert request.method == "POST"
    assert request.headers["X-Api-Key"] == "SUPER-SECRET"
    # Body placeholders render as text, like the vendor's own examples.
    assert json.loads(request.content) == {"q": "python", "page": "1"}
    # `final_url` travels back to the UI and run records, so the path key is
    # scrubbed even though the request itself carried it.
    assert "SUPER-SECRET" not in page.final_url


def test_json_list_paginates_urls_and_bodies():
    get_provider = JsonListProvider(
        {"url": "https://api.example/jobs?page={page}", "max_pages": 2}, api_key="K"
    )
    assert get_provider.results_url() == "https://api.example/jobs?page=1"
    assert get_provider.next_page_url(_json_page({})) == "https://api.example/jobs?page=2"
    assert get_provider.next_page_url(_json_page({})) is None  # max_pages reached

    post_provider = JsonListProvider(
        {
            "url": "https://jooble.example/api/{api_key}",
            "method": "POST",
            "body": {"page": "{page}"},
            "max_pages": 2,
        },
        api_key="K",
    )
    # A body-paginated vendor keeps the *same* URL; the page rides in the body.
    assert post_provider.next_page_url(_json_page({})) == "https://jooble.example/api/K"
    assert post_provider.request_spec("https://jooble.example/api/K") == (
        "POST",
        {"page": "2"},
    )

    # One page is the default: a `{page}`-less, body-less config never pages.
    single = JsonListProvider({"url": "https://api.example/jobs"})
    assert single.next_page_url(_json_page({})) is None


def test_json_list_rejects_bad_methods_and_bodies():
    with pytest.raises(ValueError, match="unsupported method"):
        JsonListProvider({"url": "https://api.example/jobs", "method": "PUT"}).request_spec("x")
    with pytest.raises(ValueError, match="'body'"):
        JsonListProvider({"url": "https://api.example/jobs", "method": "POST"}).request_spec("x")

ADZUNA_PAYLOAD = {
    "results": [
        {
            "id": "123456",
            "title": "Backend Engineer",
            "redirect_url": "https://www.adzuna.com.br/details/123456",
            "created": "2026-08-01T10:00:00Z",
            "description": "Build <b>APIs</b> with Python",
            "company": {"display_name": "Acme"},
            "location": {"display_name": "Sao Paulo, SP"},
        }
    ]
}

JOOBLE_PAYLOAD = {
    "totalCount": 1,
    "jobs": [
        {
            "id": 42,
            "title": "Platform Engineer",
            "link": "https://br.jooble.org/jdp/42",
            "company": "Globex",
            "location": "Remote, Brazil",
            "updated": "2026-07-30T00:00:00.0000000",
            "snippet": "Kubernetes <em>and</em> Go",
        }
    ],
}

JSEARCH_PAYLOAD = {
    "data": [
        {
            "job_id": "abc",
            "job_title": "SRE",
            "job_apply_link": "https://example.com/jobs/abc",
            "employer_name": "Initech",
            "job_city": "Lisbon",
            "job_posted_at_datetime_utc": "2026-06-01T00:00:00.000Z",
            "job_description": "Own <b>SLOs</b>",
        }
    ]
}


def test_adzuna_provider_builds_keyed_urls_and_parses_jobs():
    provider = AdzunaProvider(
        {"app_id": "app123", "query": "python", "country": "br", "max_pages": 3},
        api_key="SECRET",
    )
    url = provider.results_url()
    assert url.startswith("https://api.adzuna.com/v1/api/jobs/br/search/1?")
    assert "app_id=app123" in url
    assert "app_key=SECRET" in url
    assert "what=python" in url
    # A read must not advance the page; only `next_page_url` does.
    assert provider.results_url() == url
    assert provider.paginated is True
    second = provider.next_page_url(_json_page({}))
    assert "/br/search/2?" in second
    assert "app_key=SECRET" in second

    jobs = provider.parse(_json_page(ADZUNA_PAYLOAD))
    assert [job.title for job in jobs] == ["Backend Engineer"]
    assert jobs[0].company == "Acme"
    assert jobs[0].external_id == "123456"
    assert jobs[0].posted_date == date(2026, 8, 1)
    assert jobs[0].tags == ["Sao Paulo, SP"]
    assert jobs[0].description == "Build APIs with Python"


def test_adzuna_requires_the_key_and_the_app_id():
    with pytest.raises(ValueError, match="API key"):
        AdzunaProvider({"app_id": "app123"}).results_url()
    with pytest.raises(ValueError, match="app_id"):
        AdzunaProvider({}, api_key="SECRET").results_url()


def test_jooble_provider_posts_the_page_number_and_parses_jobs():
    provider = JoobleProvider(
        {"query": "python", "location": "Brazil", "max_pages": 2}, api_key="K"
    )
    url = provider.results_url()
    assert url == "https://jooble.org/api/K"  # the key is a path segment
    method, body = provider.request_spec(url)
    assert method == "POST"
    assert body == {"keywords": "python", "location": "Brazil", "page": "1"}
    assert provider.pagination_in_body is True
    assert provider.next_page_url(_json_page({})) == url  # same URL, new body page
    assert provider.request_spec(url)[1]["page"] == "2"

    jobs = provider.parse(_json_page(JOOBLE_PAYLOAD))
    assert [job.title for job in jobs] == ["Platform Engineer"]
    assert jobs[0].company == "Globex"
    assert jobs[0].url == "https://br.jooble.org/jdp/42"
    assert jobs[0].external_id == "42"
    assert jobs[0].posted_date == date(2026, 7, 30)
    assert jobs[0].tags == ["Remote, Brazil"]
    assert jobs[0].description == "Kubernetes and Go"


def test_jsearch_provider_sends_the_rapidapi_headers_and_parses_jobs():
    provider = JSearchProvider({"query": "python in Brazil", "max_pages": 2}, api_key="KEY")
    url = provider.results_url()
    assert url.startswith("https://jsearch.p.rapidapi.com/search?")
    assert "query=python+in+Brazil" in url
    assert "page=1" in url
    assert "country=br" in url
    assert "page=2" in provider.next_page_url(_json_page({}))

    headers = provider._key_headers()
    assert headers["X-RapidAPI-Key"] == "KEY"
    assert headers["X-RapidAPI-Host"] == "jsearch.p.rapidapi.com"

    jobs = provider.parse(_json_page(JSEARCH_PAYLOAD))
    assert [job.title for job in jobs] == ["SRE"]
    assert jobs[0].company == "Initech"
    assert jobs[0].posted_date == date(2026, 6, 1)
    assert jobs[0].tags == ["Lisbon"]
    assert jobs[0].description == "Own SLOs"


@pytest.mark.parametrize(
    ("name", "cls"),
    (("adzuna", AdzunaProvider), ("jooble", JoobleProvider), ("jsearch", JSearchProvider)),
)
def test_keyed_json_vendors_are_registered_with_their_contract(name, cls):
    provider = get_discovery_provider(name, {"app_id": "x", "query": "y"}, "KEY")
    assert isinstance(provider, cls)
    assert provider.family == "search_api"
    assert provider.requires_key is True
    # One page per run unless the source asks for more (cost control).
    assert provider.max_pages() == 1

    metadata = cls.config_metadata()
    # The key is a *credential*, never part of the published config contract.
    assert "api_key" not in metadata["required"] + metadata["optional"]
    assert "api_key" not in json.dumps(metadata["example"])


def test_check_credentials_reports_only_a_missing_key():
    """What the scrape task calls to skip a keyed run instead of getting a 401."""
    with pytest.raises(ValueError, match="API key") as missing_key:
        DiscoveryScraper("jooble", {"query": "python"}).check_credentials(has_api_key=False)
    # The message has to say *where* the key is added.
    assert "Authentication panel" in str(missing_key.value)
    with pytest.raises(ValueError, match="API key"):
        DiscoveryScraper("adzuna", {"app_id": "app1"}).check_credentials(has_api_key=False)

    # A stored key is enough — and so is knowing that one exists.
    DiscoveryScraper("jooble", {"query": "python"}, "KEY").check_credentials(has_api_key=False)
    DiscoveryScraper("jooble", {"query": "python"}).check_credentials(has_api_key=True)

    # Config mistakes surface through the same call, so they fail fast as well.
    with pytest.raises(ValueError, match="app_id"):
        DiscoveryScraper("adzuna", {}).check_credentials(has_api_key=True)

    # Providers whose config never carries the key are unaffected.
    DiscoveryScraper("json_list", {"url": "https://api.example/jobs"}).check_credentials(
        has_api_key=False
    )
    DiscoveryScraper("greenhouse", {"board_token": "acme"}).check_credentials(
        has_api_key=False
    )


# --- Additional ATS providers (endpoint shapes verified live) ------------------


SMARTRECRUITERS_PAYLOAD = {
    "offset": 0,
    "limit": 1,
    "totalFound": 1,
    "content": [
        {
            "id": "744000150368199",
            "name": "Maintenance Technician",
            "company": {"identifier": "acme", "name": "Acme Group"},
            "releasedDate": "2026-09-18T13:03:07.324Z",
            "location": {
                "city": "Lincolnton",
                "fullLocation": "Lincolnton, NC, United States",
            },
            "typeOfEmployment": {"id": "permanent", "label": "Full-time"},
            "department": {},
            "function": {"id": "manufacturing", "label": "Manufacturing"},
        }
    ],
}


def test_smartrecruiters_provider_parses_postings():
    provider = SmartRecruitersProvider({"company": "acme", "max_results": 5})
    assert provider.results_url() == (
        "https://api.smartrecruiters.com/v1/companies/acme/postings?limit=5"
    )
    jobs = provider.parse(_json_page(SMARTRECRUITERS_PAYLOAD))
    assert jobs[0].title == "Maintenance Technician"
    # The display name wins over the identifier; empty facets are dropped.
    assert jobs[0].company == "Acme Group"
    assert jobs[0].url == "https://jobs.smartrecruiters.com/acme/744000150368199"
    assert jobs[0].posted_date == date(2026, 9, 18)
    assert jobs[0].external_id == "744000150368199"
    assert jobs[0].tags == [
        "Full-time",
        "Manufacturing",
        "Lincolnton, NC, United States",
    ]


RECRUITEE_PAYLOAD = {
    "offers": [
        {
            "id": 2744472,
            "title": "Technical Customer Support",
            "company_name": "Acme",
            "city": "Utrecht",
            "country_code": "NL",
            "created_at": "2026-09-14 07:17:14 UTC",
            "careers_url": "https://jobs.acme.example/o/technical-customer-support",
            "tags": ["support"],
            "department": "Customer Success",
            "description": "<p>Help <b>customers</b>.</p>",
        }
    ]
}


def test_recruitee_provider_parses_offers():
    provider = RecruiteeProvider({"company": "acme"})
    assert provider.results_url() == "https://acme.recruitee.com/api/offers/"
    jobs = provider.parse(_json_page(RECRUITEE_PAYLOAD))
    assert jobs[0].title == "Technical Customer Support"
    assert jobs[0].company == "Acme"
    assert jobs[0].url == "https://jobs.acme.example/o/technical-customer-support"
    assert jobs[0].posted_date == date(2026, 9, 14)
    assert jobs[0].tags == ["support", "Customer Success", "Utrecht, NL"]
    assert jobs[0].description is not None
    assert "Help customers" in jobs[0].description


PERSONIO_XML = """
<workzag-jobs>
  <position>
    <id>1834171</id>
    <subcompany>Acme SE &amp; Co. KG</subcompany>
    <office>Munich</office>
    <additionalOffices><office>Berlin</office></additionalOffices>
    <department>Product and Tech</department>
    <recruitingCategory>Engineering</recruitingCategory>
    <name>Staff Software Engineer</name>
    <jobDescriptions>
      <jobDescription>
        <name>description</name>
        <value>&lt;p&gt;Build &lt;b&gt;APIs&lt;/b&gt;.&lt;/p&gt;</value>
      </jobDescription>
    </jobDescriptions>
    <employmentType>permanent</employmentType>
    <seniority>experienced</seniority>
    <createdAt>2024-11-13T14:10:41+00:00</createdAt>
  </position>
  <position><name>No id, skipped</name></position>
</workzag-jobs>
"""


def _xml_page(xml: str) -> ScrapedPage:
    return ScrapedPage(
        html_content=xml,
        status_code=200,
        final_url="https://acme.jobs.personio.de/xml",
    )


def test_personio_provider_parses_xml_feed():
    provider = PersonioProvider(
        {
            "company": "acme",
            "url_tpl": "https://{company}.jobs.personio.de/job/{id}?language=en",
        }
    )
    assert provider.results_url() == "https://acme.jobs.personio.de/xml"
    jobs = provider.parse(_xml_page(PERSONIO_XML))
    assert len(jobs) == 1  # the position without an <id> is skipped
    assert jobs[0].title == "Staff Software Engineer"
    # XML entities are decoded by the parser.
    assert jobs[0].company == "Acme SE & Co. KG"
    assert jobs[0].url == "https://acme.jobs.personio.de/job/1834171?language=en"
    assert jobs[0].posted_date == date(2024, 11, 13)
    assert jobs[0].external_id == "1834171"
    assert jobs[0].tags == [
        "Product and Tech",
        "Engineering",
        "permanent",
        "experienced",
        "Munich, Berlin",
    ]
    assert jobs[0].description is not None
    assert "Build APIs" in jobs[0].description


def test_personio_provider_requires_url_tpl_and_valid_xml():
    with pytest.raises(ValueError, match="url_tpl"):
        PersonioProvider({"company": "acme"}).parse(_xml_page(PERSONIO_XML))
    provider = PersonioProvider({"company": "acme", "url_tpl": "https://x.example/{id}"})
    with pytest.raises(ValueError, match="valid XML"):
        provider.parse(_xml_page("<workzag-jobs><position>"))


WORKDAY_PAYLOAD = {
    "total": 1,
    "jobPostings": [
        {
            "title": "Senior Software Engineer",
            "externalPath": "/job/Germany-Remote/Senior-Software-Engineer_JR2017366",
            "locationsText": "6 Locations",
            "postedOn": "Posted Today",
            "bulletFields": ["JR2017366"],
        }
    ],
}


def test_workday_provider_parses_and_builds_job_urls():
    provider = WorkdayProvider(
        {
            "host": "acme.wd1.myworkdayjobs.com",
            "tenant": "acme",
            "site": "AcmeCareers",
            "company": "Acme",
        }
    )
    assert provider.results_url() == (
        "https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/AcmeCareers/jobs"
    )
    body = provider._request_payload()
    assert body["appliedFacets"] == {}
    assert body["offset"] == 0
    assert body["searchText"] == ""

    jobs = provider.parse(_json_page(WORKDAY_PAYLOAD))
    assert jobs[0].title == "Senior Software Engineer"
    assert jobs[0].company == "Acme"
    assert jobs[0].url == (
        "https://acme.wd1.myworkdayjobs.com/en-US/AcmeCareers"
        "/job/Germany-Remote/Senior-Software-Engineer_JR2017366"
    )
    assert jobs[0].external_id == "JR2017366"
    assert jobs[0].tags == ["6 Locations", "JR2017366"]
    # `postedOn` is a human label ("Posted Today"), so no date is derived.
    assert jobs[0].posted_date is None


def test_workday_provider_requires_host_tenant_and_site():
    with pytest.raises(ValueError, match="tenant"):
        WorkdayProvider({"host": "acme.wd1.myworkdayjobs.com", "site": "AcmeCareers"}).results_url()


def test_new_ats_providers_are_registered():
    for name in ("smartrecruiters", "recruitee", "personio", "workday"):
        provider = get_discovery_provider(name, {})
        assert provider.family == "ats"
        assert provider.requires_key is False


def test_google_cse_provider_extracts_links_and_next_offset():
    provider = GoogleCseProvider({"query": "site:acme.example python", "cx": "cse-1"}, "KEY-123")
    assert "key=KEY-123" in provider.results_url()
    page = _json_page(
        {
            "items": [
                {"link": "https://acme.example/jobs/1"},
                {"link": "https://acme.example/jobs/2"},
            ],
            "queries": {"nextPage": [{"startIndex": 11}]},
        }
    )
    assert provider.discover_urls(page) == [
        "https://acme.example/jobs/1",
        "https://acme.example/jobs/2",
    ]
    next_url = provider.next_page_url(page)
    assert next_url and "start=11" in next_url


def test_twostage_parse_prefers_json_ld_then_selectors():
    provider = GoogleCseProvider({"query": "x", "cx": "c"}, "K")

    structured = ScrapedPage(
        html_content=CAREER_PAGE_HTML,
        status_code=200,
        final_url="https://acme.example/jobs/42",
    )
    jobs = provider.parse(structured)
    assert jobs and jobs[0].title == "Senior Python Engineer"

    fallback = ScrapedPage(
        html_content=DETAIL_HTML,
        status_code=200,
        final_url="https://acme.example/jobs/42",
    )
    jobs = provider.parse(fallback)
    assert jobs and jobs[0].title == "Senior Python Engineer"
    assert jobs[0].company == "Acme Corp"


SERPAPI_LINKEDIN_PAYLOAD = {
    "jobs_results": [
        {
            "title": "Python Engineer",
            "link": "https://www.google.com/search?ibp=htl;jobs&q=python",
            "job_google_link": "https://www.google.com/search?ibp=htl;jobs&q=python#fpstate",
            "company_name": "Acme",
            "location": "Remote, Brazil",
            "extensions": ["Full-time", "Senior level"],
            "detected_extensions": {"posted_at": "3 days ago", "work_from_home": True},
            "job_id": "srv:1",
            "job_highlights": [{"title": "Qualifications", "items": ["Python", "FastAPI"]}],
            "apply_options": [
                {
                    "title": "Acme Careers",
                    "link": "https://acme.example/jobs/1",
                    "apply_link": "https://acme.example/apply/1",
                }
            ],
        },
        {
            "title": "Data Engineer",
            "job_google_link": "https://www.google.com/search?ibp=htl;jobs&q=data",
            "apply_options": [{"link": "https://www.linkedin.com/jobs/view/2"}],
        },
        {"title": "No link at all"},
    ],
    "serpapi_pagination": {"next": "https://serpapi.com/search?engine=linkedin_jobs&start=11"},
}

SERPAPI_INDEED_PAYLOAD = {
    "jobs_results": [
        {"title": "Backend Engineer", "link": "https://br.indeed.com/viewjob?jk=abc123"},
    ]
}

BRIGHTDATA_LINKEDIN_HTML = """
<html><body>
<a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/7">Job 7</a>
<a href="https://www.linkedin.com/jobs/view/8">Job 8</a>
</body></html>
"""

BRIGHTDATA_LISTING_HTML = """
<html><body>
<ul class="jobs-search-results__list">
  <li class="jobs-search-results__list-item">
    <a class="job-card-container__link" href="/jobs/view/7?refId=abc">Python Engineer</a>
    <span class="artdeco-entity-lockup__subtitle">Acme</span>
    <ul class="job-card-container__metadata-wrapper"><li>Remote, Brazil</li></ul>
  </li>
  <li class="jobs-search-results__list-item">
    <a class="job-card-container__link" href="/jobs/view/8">Data Engineer</a>
    <span class="artdeco-entity-lockup__subtitle">Globex</span>
  </li>
</ul>
</body></html>
"""

BRIGHTDATA_LISTING_SELECTORS = {
    "parse_listing": True,
    "item_selector": "li.jobs-search-results__list-item",
    "title_selector": "a.job-card-container__link",
    "url_selector": "a.job-card-container__link",
    "company_selector": ".artdeco-entity-lockup__subtitle",
    "location_selector": ".job-card-container__metadata-wrapper li",
}


class _FakeResponse:
    """Minimal stand-in for ``httpx.Response``."""

    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.content = text.encode()
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeBrightDataClient:
    """Records every POST (url + payload) and replays scripted responses."""

    def __init__(self, *responses: _FakeResponse):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, *, headers=None, json=None, **kwargs):
        self.calls.append((url, json))
        return self._responses.pop(0)


def _patch_brightdata_client(monkeypatch, fake: _FakeBrightDataClient) -> None:
    import scrapers.discovery as discovery

    monkeypatch.setattr(discovery.httpx, "AsyncClient", lambda *a, **k: fake)


def test_serpapi_provider_builds_url_and_parses_results():
    provider = SerpApiProvider(
        {"engine": "linkedin_jobs", "query": "Python Remote Brazil", "num": 20}, "KEY-1"
    )
    url = provider.results_url()
    assert "api_key=KEY-1" in url
    assert "engine=linkedin_jobs" in url
    assert "num=20" in url

    page = _json_page(SERPAPI_LINKEDIN_PAYLOAD)
    # `apply_options[].link` is the real board URL; the google.com/ibp=htl links
    # only work inside a browser session (they were picked first before).
    assert provider.discover_urls(page) == [
        "https://acme.example/jobs/1",
        "https://www.linkedin.com/jobs/view/2",
    ]
    assert provider.next_page_url(page) == (
        "https://serpapi.com/search?engine=linkedin_jobs&start=11"
    )

    indeed = SerpApiProvider({"engine": "indeed", "query": "python"}, "K")
    assert indeed.discover_urls(_json_page(SERPAPI_INDEED_PAYLOAD)) == [
        "https://br.indeed.com/viewjob?jk=abc123",
    ]


def test_serpapi_link_source_google_restores_serp_links():
    provider = SerpApiProvider(
        {"engine": "google_jobs", "query": "python", "link_source": "google"}, "K"
    )
    assert provider.discover_urls(_json_page(SERPAPI_LINKEDIN_PAYLOAD)) == [
        "https://www.google.com/search?ibp=htl;jobs&q=python",
        "https://www.google.com/search?ibp=htl;jobs&q=data",
    ]


def test_serpapi_results_mode_parses_jobs_without_detail_fetches():
    """`parse_mode: results` is the cheap path: one request per run."""
    provider = SerpApiProvider(
        {"engine": "google_jobs", "query": "python", "parse_mode": "results"}, "K"
    )
    assert provider.parse_listing() is True
    page = _json_page(SERPAPI_LINKEDIN_PAYLOAD)

    # Nothing to fetch per job, so the worker stays on a single paid call.
    assert provider.discover_urls(page) == []

    jobs = provider.parse(page)
    assert [job.title for job in jobs] == ["Python Engineer", "Data Engineer"]
    first = jobs[0]
    assert first.company == "Acme"
    assert first.url == "https://acme.example/jobs/1"
    assert first.external_id == "srv:1"
    assert first.tags == ["Remote, Brazil", "Full-time", "Senior level"]
    assert first.description == "Python FastAPI"
    # "3 days ago" becomes a concrete date.
    assert first.posted_date == date.today() - timedelta(days=3)
    # Jobs[1] falls back to the LinkedIn link (no apply_options); the third
    # result has no link anywhere and is dropped instead of stored unreachable.
    assert jobs[1].url == "https://www.linkedin.com/jobs/view/2"


def test_serpapi_results_mode_honours_max_results_and_iso_posts():
    provider = SerpApiProvider({"query": "python", "parse_mode": "results", "max_results": 2}, "K")
    payload = {
        "jobs_results": [
            {
                "title": "A",
                "apply_options": [{"link": "https://a.example/1"}],
                "detected_extensions": {"posted_at": "2026-08-01T10:00:00Z"},
            },
            {"title": "B", "apply_options": [{"link": "https://a.example/2"}]},
            {"title": "C", "apply_options": [{"link": "https://a.example/3"}]},
        ]
    }
    jobs = provider.parse(_json_page(payload))
    assert [job.title for job in jobs] == ["A", "B"]
    assert jobs[0].posted_date == date(2026, 8, 1)


def test_relative_age_parses_serp_labels():
    assert relative_age("Just posted") == date.today().isoformat()
    assert relative_age("30+ days ago") == (date.today() - timedelta(days=30)).isoformat()
    assert relative_age("2 weeks ago") == (date.today() - timedelta(days=14)).isoformat()
    assert relative_age("5 hours ago") == date.today().isoformat()
    assert relative_age("last month") is None
    assert relative_age(None) is None


def test_parse_html_list_reads_relative_dates_and_descriptions():
    """Shared listing parser: aggregators and search providers use the same card."""
    page = ScrapedPage(
        html_content="""
        <ul>
          <li class="card">
            <h2><a href="/jobs/1">Python Engineer</a></h2>
            <span class="company">Acme</span>
            <span class="location">Remote</span>
            <time>3 days ago</time>
            <p class="snippet">Fast-paced team.</p>
          </li>
          <li class="card"><h2><a href="/jobs/2">No date</a></h2></li>
        </ul>
        """,
        status_code=200,
        final_url="https://boards.example/list",
    )
    jobs = parse_html_list(
        page,
        {
            "item_selector": "li.card",
            "title_selector": "h2 a",
            "url_selector": "h2 a",
            "company_selector": ".company",
            "location_selector": ".location",
            "date_selector": "time",
            "description_selector": ".snippet",
        },
    )
    assert [job.title for job in jobs] == ["Python Engineer", "No date"]
    assert jobs[0].url == "https://boards.example/jobs/1"
    assert jobs[0].company == "Acme"
    assert jobs[0].posted_date == date.today() - timedelta(days=3)
    assert jobs[0].description == "Fast-paced team. • Location: Remote"
    # No location/date/description nodes → the old fallbacks still apply.
    assert jobs[1].posted_date is None
    assert jobs[1].description is None


def test_brightdata_provider_metadata_and_parsing():
    provider = BrightDataProvider({"engine": "linkedin", "query": "Python"}, "KEY-2")
    assert provider.requires_key is True
    assert provider.family == "search_api"
    assert "linkedin.com/jobs/search" in provider._target_url()
    assert (
        "br.indeed.com" in BrightDataProvider({"engine": "indeed", "query": "python"})._target_url()
    )
    # A custom target URL (config `url`/`url_tpl`) overrides the engine default.
    custom = BrightDataProvider(
        {"url_tpl": "https://{host}/jobs?q={query}", "host": "acme.example", "query": "python"}
    )
    assert custom._target_url() == "https://acme.example/jobs?q=python"
    with pytest.raises(ValueError, match="target URL"):
        BrightDataProvider({"url_tpl": "https://acme.example?q={missing}"})._target_url()

    page = ScrapedPage(
        html_content=BRIGHTDATA_LINKEDIN_HTML,
        status_code=200,
        final_url="https://api.brightdata.com/request",
    )
    assert provider.discover_urls(page) == [
        "https://www.linkedin.com/jobs/view/7",
        "https://www.linkedin.com/jobs/view/8",
    ]
    # Metadata now states what a working source needs (it used to require nothing).
    metadata = BrightDataProvider.config_metadata()
    assert metadata["required"] == ("zone",)
    assert metadata["example"]["zone"] == "web_unlocker1"


def test_brightdata_endpoint_modes_follow_the_zone_type():
    """LinkedIn/Indeed are rendered by the Unlocker; SERP zones use /serp/req."""
    assert BrightDataProvider({"engine": "linkedin"}).endpoint_mode() == "unlocker"
    assert BrightDataProvider({"engine": "indeed"}).endpoint_mode() == "unlocker"
    assert BrightDataProvider({"engine": "google", "query": "python"}).endpoint_mode() == "serp"

    unlocker = BrightDataProvider({"engine": "linkedin", "zone": "web_unlocker1"})
    assert unlocker.results_url() == "https://api.brightdata.com/request"

    serp = BrightDataProvider(
        {"engine": "google", "query": "python", "zone": "serp_api1", "customer": "hl_123"}
    )
    assert serp.results_url() == (
        "https://api.brightdata.com/serp/req?customer=hl_123&zone=serp_api1"
    )

    # An explicit mode wins over the engine heuristic, and an explicit URL lets
    # a future endpoint change be configured without a release.
    forced = BrightDataProvider({"engine": "linkedin", "endpoint": "serp", "zone": "z"})
    assert forced.endpoint_mode() == "serp"
    piped = BrightDataProvider({"engine": "linkedin", "endpoint": "https://proxy.example/render"})
    assert piped.results_url() == "https://proxy.example/render"


def test_brightdata_robots_url_targets_the_board_not_the_api():
    provider = BrightDataProvider({"engine": "linkedin", "query": "python"})
    assert provider.robots_url(provider.results_url()) == (
        "https://www.linkedin.com/jobs/search?keywords=python"
    )
    # Detail URLs already are real board URLs.
    assert provider.robots_url("https://www.linkedin.com/jobs/view/7") == (
        "https://www.linkedin.com/jobs/view/7"
    )
    scraper = DiscoveryScraper("brightdata", {"engine": "linkedin", "query": "python"})
    assert scraper.robots_url("https://api.brightdata.com/request").startswith(
        "https://www.linkedin.com/jobs/search"
    )


def test_brightdata_parses_the_results_page_in_listing_mode():
    """`parse_listing: true` costs one render per run instead of one per job."""
    provider = BrightDataProvider(
        {"engine": "linkedin", "query": "python", **BRIGHTDATA_LISTING_SELECTORS}
    )
    assert provider.parse_listing() is True
    page = ScrapedPage(
        html_content=BRIGHTDATA_LISTING_HTML,
        status_code=200,
        final_url="https://www.linkedin.com/jobs/search?keywords=python",
    )
    # No detail URLs means the worker never issues a paid fetch per job.
    assert provider.discover_urls(page) == []

    jobs = provider.parse(page)
    assert [job.title for job in jobs] == ["Python Engineer", "Data Engineer"]
    assert jobs[0].company == "Acme"
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/7?refId=abc"
    assert jobs[0].description == "Location: Remote, Brazil"
    assert jobs[1].url == "https://www.linkedin.com/jobs/view/8"
    assert jobs[1].description is None


@pytest.mark.asyncio
async def test_brightdata_fetch_honours_the_url_it_is_given(monkeypatch):
    """Regression: re-rendering the SERP for a *detail* URL burned paid calls."""
    provider = BrightDataProvider(
        {"engine": "linkedin", "query": "python", "zone": "web_unlocker1"}, "KEY-2"
    )
    fake = _FakeBrightDataClient(
        _FakeResponse(BRIGHTDATA_LINKEDIN_HTML), _FakeResponse("<html>detail</html>")
    )
    _patch_brightdata_client(monkeypatch, fake)

    results = await provider.fetch(provider.results_url())
    assert fake.calls[0][0] == "https://api.brightdata.com/request"
    assert fake.calls[0][1]["url"] == "https://www.linkedin.com/jobs/search?keywords=python"
    assert fake.calls[0][1]["zone"] == "web_unlocker1"
    assert results.final_url.startswith("https://www.linkedin.com/jobs/search")

    detail = await provider.fetch("https://www.linkedin.com/jobs/view/7")
    endpoint, payload = fake.calls[1]
    # Same (paid) endpoint, but the target is the detail page itself.
    assert endpoint == "https://api.brightdata.com/request"
    assert payload["url"] == "https://www.linkedin.com/jobs/view/7"
    assert detail.final_url == "https://www.linkedin.com/jobs/view/7"


@pytest.mark.asyncio
async def test_brightdata_serp_mode_sends_customer_in_the_query(monkeypatch):
    provider = BrightDataProvider(
        {"engine": "google", "query": "python", "endpoint": "serp", "zone": "z1", "customer": "hl"}
    )
    fake = _FakeBrightDataClient(_FakeResponse("<html></html>"))
    _patch_brightdata_client(monkeypatch, fake)

    await provider.fetch(provider.results_url())
    url, payload = fake.calls[0]
    assert url == "https://api.brightdata.com/serp/req?customer=hl&zone=z1"
    # /serp/req takes the zone in the query string, so the body stays minimal.
    assert "zone" not in payload


def test_brightdata_pagination_needs_page_tpl_and_respects_max_pages():
    provider = BrightDataProvider(
        {
            "engine": "linkedin",
            "query": "python",
            "zone": "z1",
            "page_tpl": "{page}0",
            "max_pages": 2,
        }
    )
    page = ScrapedPage(html_content="<html></html>", status_code=200, final_url="u")
    assert provider.next_page_url(page) == "https://api.brightdata.com/request"
    assert "start=20" in provider._target_url()
    # max_pages stops the loop before a third paid render.
    assert provider.next_page_url(page) is None

    # Without `page_tpl` there is a single render, exactly like before.
    single = BrightDataProvider({"engine": "linkedin", "query": "python", "zone": "z1"})
    assert single.next_page_url(page) is None


def test_discovery_registry_and_scraper_dispatch():
    with pytest.raises(ValueError):
        get_discovery_provider("does_not_exist")

    scraper = DiscoveryScraper("google_cse", {"query": "q", "cx": "c"}, "KEY")
    assert scraper.provider.api_key == "KEY"
    assert scraper.first_fetch_url("http://ignored") != "http://ignored"

    source = SimpleNamespace(
        type=SourceType.discovery,
        config={"provider": "greenhouse", "board_token": "acme"},
    )
    dispatched = get_scraper(source)
    assert dispatched.provider.provider_name == "greenhouse"

    with pytest.raises(ValueError):
        get_scraper(SimpleNamespace(type=SourceType.discovery, config={}))


# --- fetch_html transport ----------------------------------------------------
# `fetch_html` owns redirects, the SSRF guard and the response size cap, so the
# POST support keyed APIs need is tested here (with a mocked transport) instead
# of in the provider tests.

_OFFLINE_URL = "https://api.example.com/jobs"


def _patch_httpx_transport(monkeypatch, handler) -> None:
    """Route the client ``fetch_html`` creates through an in-memory transport."""
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(utils.httpx, "AsyncClient", factory)


@pytest.fixture
def offline_fetch(monkeypatch):
    """Skip SSRF resolution: these tests never touch the network."""
    monkeypatch.setattr(utils.settings, "scraper_allow_private_networks", True)


async def test_fetch_html_posts_a_json_body_with_auth_headers(monkeypatch, offline_fetch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="<html>ok</html>")

    _patch_httpx_transport(monkeypatch, handler)
    page = await fetch_html(
        _OFFLINE_URL,
        method="POST",
        json_body={"keywords": "python", "page": 2},
        auth=FetchAuth(headers={"X-RapidAPI-Key": "SECRET"}),
    )

    assert page.status_code == 200
    assert page.html_content == "<html>ok</html>"
    assert page.final_url == _OFFLINE_URL

    request = seen[0]
    assert request.method == "POST"
    assert json.loads(request.content) == {"keywords": "python", "page": 2}
    assert request.headers["x-rapidapi-key"] == "SECRET"
    assert request.headers["accept-language"] == "en-US,en;q=0.9"
    assert request.headers["content-type"] == "application/json"


async def test_fetch_html_defaults_to_get_without_a_body(monkeypatch, offline_fetch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="<html>ok</html>")

    _patch_httpx_transport(monkeypatch, handler)
    await fetch_html(_OFFLINE_URL)

    assert seen[0].method == "GET"
    assert seen[0].content == b""


async def test_fetch_html_can_surface_the_provider_error_body(monkeypatch, offline_fetch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid api key", "api_key": "SECRET"})

    _patch_httpx_transport(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        await fetch_html(_OFFLINE_URL, read_error_body=True)

    # The scrape worker classifies 401/403 as "degraded" from this attribute.
    assert excinfo.value.response.status_code == 401
    assert "invalid api key" in str(excinfo.value)
    # Neither the key echo nor the request URL may leak it.
    assert "SECRET" not in str(excinfo.value)


async def test_fetch_html_omits_the_error_body_unless_asked(monkeypatch, offline_fetch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="provider exploded with detail")

    _patch_httpx_transport(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        await fetch_html(_OFFLINE_URL)

    assert excinfo.value.response.status_code == 500
    assert "provider exploded" not in str(excinfo.value)


async def test_fetch_html_follows_redirects_before_reading(monkeypatch, offline_fetch):
    hops: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hops.append(request.url.path)
        if request.url.path == "/jobs":
            return httpx.Response(302, headers={"location": "/moved/jobs"})
        return httpx.Response(200, text="<html>page 2</html>")

    _patch_httpx_transport(monkeypatch, handler)
    page = await fetch_html(_OFFLINE_URL)

    assert hops == ["/jobs", "/moved/jobs"]
    assert page.final_url == "https://api.example.com/moved/jobs"
    assert page.html_content == "<html>page 2</html>"


async def test_fetch_html_blocks_unsafe_targets_before_a_post(monkeypatch):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(str(request.url))
        return httpx.Response(200, text="should never be reached")

    _patch_httpx_transport(monkeypatch, handler)
    monkeypatch.setattr(utils.settings, "scraper_allow_private_networks", False)

    with pytest.raises(ValueError, match="Blocked address"):
        await fetch_html("http://127.0.0.1:5432/jobs", method="POST", json_body={"a": 1})
    # The guard runs before the body is ever sent.
    assert calls == []


async def test_fetch_html_stops_after_too_many_redirects(monkeypatch, offline_fetch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/loop"})

    _patch_httpx_transport(monkeypatch, handler)
    with pytest.raises(ValueError, match="Too many redirects"):
        await fetch_html(_OFFLINE_URL)


def test_redact_sensitive_hides_json_key_fields():
    assert "SECRET" not in redact_sensitive('{"error": "invalid", "api_key": "SECRET"}')


def test_redact_sensitive_hides_vendor_query_param_names():
    """Vendors name the query key differently: `app_key`, `subscription-key`."""
    for name in ("api_key", "apikey", "app_key", "subscription-key", "X-Api-Key"):
        message = redact_sensitive(f"https://api.example/search?{name}=SECRET&q=python")
        assert "SECRET" not in message, name
        assert "q=python" in message, name
    # A parameter that merely *contains* "key" is not a credential.
    assert "python" in redact_sensitive("https://api.example/search?keyword=python")


def test_redact_sensitive_hides_a_key_given_by_the_caller():
    """Keys in a URL *path* (Jooble) can only be scrubbed when passed in."""
    message = "HTTP 404 from https://jooble.org/api/9f8e7d6c5b/jobs"
    assert "9f8e7d6c5b" in redact_sensitive(message)
    assert "9f8e7d6c5b" not in redact_sensitive(message, "9f8e7d6c5b")


async def test_fetch_html_error_message_never_echoes_the_api_key(monkeypatch, offline_fetch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    _patch_httpx_transport(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        await fetch_html(
            "https://jooble.org/api/SUPER-SECRET-KEY/jobs",
            method="POST",
            json_body={"keywords": "python"},
            auth=FetchAuth(api_key="SUPER-SECRET-KEY"),
            read_error_body=True,
        )

    # The path segment is part of the request URL, so it must be scrubbed.
    assert "SUPER-SECRET-KEY" not in str(excinfo.value)

