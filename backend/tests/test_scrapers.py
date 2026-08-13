"""Unit tests for the scraper implementations (no DB/network required)."""

import json
from types import SimpleNamespace

import pytest
from scrapers.aggregator import GenericHtmlListScraper, get_aggregator_adapter
from scrapers.career_page import CareerPageScraper
from scrapers.discovery import (
    BrightDataProvider,
    DiscoveryScraper,
    GoogleCseProvider,
    GreenhouseProvider,
    SerpApiProvider,
    get_discovery_provider,
)
from scrapers.registry import get_scraper
from scrapers.rss import RSSScraper
from scrapers.types import RawJob, ScrapedPage

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
        [RawJob(title="X", company="Y", url="https://x.example/job")]
    )
    assert normalized[0]["company"] == "Y"
    assert scraper.normalize([RawJob(title="", company="", url="")]) == []


def test_get_aggregator_adapter_unknown_raises():
    with pytest.raises(ValueError):
        get_aggregator_adapter("does_not_exist")


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

