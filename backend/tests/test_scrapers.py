"""Unit tests for the scraper implementations (no DB/network required)."""

import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest
import scrapers.utils as utils
from scrapers.aggregator import (
    EmbeddedJsonListScraper,
    GenericHtmlListScraper,
    get_aggregator_adapter,
)
from scrapers.career_page import CareerPageScraper
from scrapers.discovery import (
    BrightDataProvider,
    DiscoveryScraper,
    GoogleCseProvider,
    GreenhouseProvider,
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
from scrapers.types import RawJob, ScrapedPage
from scrapers.utils import (
    coerce_date,
    parse_json_ld_jobs,
    redact_sensitive,
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


def test_aggregator_normalize_skips_invalid():
    scraper = GenericHtmlListScraper({})
    normalized = scraper.normalize(
        [RawJob(title="X", company="Y", url="https://x.example/job", external_id="job-1")]
    )
    assert normalized[0]["company"] == "Y"
    assert normalized[0]["external_id"] == "job-1"
    assert scraper.normalize([RawJob(title="", company="", url="")]) == []
    # Whitespace-only titles are dropped, not stored as empty strings.
    assert (
        scraper.normalize(
            [RawJob(title="   ", company="Y", url="https://x.example/job")]
        )
        == []
    )


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
    assert GenericHtmlListScraper({}).discover_urls(
        _aggregator_page(DETAIL_LIST_HTML)
    ) == []


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
    raw = scraper.parse(
        _aggregator_page(DETAIL_PAGE_HTML, "https://board.example/jobs/1")
    )
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
    assert (
        provider.results_url()
        == "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
    )
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
        html_content=json.dumps(
            {"job": {"name": "Solo", "link": "https://x.example/1"}}
        ),
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
    assert scraper.first_fetch_url("https://ignored.example") == (
        "https://api.example/list"
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
        WorkdayProvider(
            {"host": "acme.wd1.myworkdayjobs.com", "site": "AcmeCareers"}
        ).results_url()


def test_new_ats_providers_are_registered():
    for name in ("smartrecruiters", "recruitee", "personio", "workday"):
        provider = get_discovery_provider(name, {})
        assert provider.family == "ats"
        assert provider.requires_key is False


def test_google_cse_provider_extracts_links_and_next_offset():
    provider = GoogleCseProvider(
        {"query": "site:acme.example python", "cx": "cse-1"}, "KEY-123"
    )
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
            "link": "https://www.linkedin.com/jobs/view/1",
            "company_name": "Acme",
        },
        {"title": "Data Engineer", "job_google_link": "https://www.linkedin.com/jobs/view/2"},
    ],
    "serpapi_pagination": {
        "next": "https://serpapi.com/search?engine=linkedin_jobs&start=11"
    },
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


def test_serpapi_provider_builds_url_and_parses_results():
    provider = SerpApiProvider(
        {"engine": "linkedin_jobs", "query": "Python Remote Brazil", "num": 20}, "KEY-1"
    )
    url = provider.results_url()
    assert "api_key=KEY-1" in url
    assert "engine=linkedin_jobs" in url
    assert "num=20" in url

    page = _json_page(SERPAPI_LINKEDIN_PAYLOAD)
    assert provider.discover_urls(page) == [
        "https://www.linkedin.com/jobs/view/1",
        "https://www.linkedin.com/jobs/view/2",
    ]
    assert provider.next_page_url(page) == (
        "https://serpapi.com/search?engine=linkedin_jobs&start=11"
    )

    indeed = SerpApiProvider({"engine": "indeed", "query": "python"}, "K")
    assert indeed.discover_urls(_json_page(SERPAPI_INDEED_PAYLOAD)) == [
        "https://br.indeed.com/viewjob?jk=abc123",
    ]


def test_brightdata_provider_metadata_and_parsing():
    provider = BrightDataProvider({"engine": "linkedin", "query": "Python"}, "KEY-2")
    assert provider.requires_key is True
    assert provider.family == "search_api"
    assert provider.results_url().startswith("https://api.brightdata.com/serp/req?")
    assert "linkedin.com/jobs/search" in provider._target_url()
    assert "br.indeed.com" in BrightDataProvider(
        {"engine": "indeed", "query": "python"}
    )._target_url()
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
        final_url="https://api.brightdata.com/serp/req",
    )
    assert provider.discover_urls(page) == [
        "https://www.linkedin.com/jobs/view/7",
        "https://www.linkedin.com/jobs/view/8",
    ]


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

