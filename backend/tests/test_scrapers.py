"""Unit tests for the scraper implementations (no DB/network required)."""

import json
import logging
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
from scrapers.ats_boards import resolve_ats_board
from scrapers.career_page import CareerPageScraper
from scrapers.discovery import (
    AdzunaProvider,
    AshbyProvider,
    BingProvider,
    BraveProvider,
    BrightDataProvider,
    DiscoveryScraper,
    GoogleCseProvider,
    GreenhouseProvider,
    JoobleProvider,
    JSearchProvider,
    JsonListProvider,
    LeverProvider,
    PersonioProvider,
    RecruiteeProvider,
    SerpApiProvider,
    SmartRecruitersProvider,
    WorkableProvider,
    WorkdayProvider,
    get_discovery_provider,
)
from scrapers.registry import get_scraper
from scrapers.rss import RSSScraper
from scrapers.types import FetchAuth, RawJob, ScrapedPage
from scrapers.utils import (
    coerce_date,
    fetch_html,
    location_allowed,
    parse_html_list,
    parse_json_ld_jobs,
    redact_sensitive,
    relative_age,
    render_path_template,
    resolve_path,
    resolve_path_values,
)

from app.models.enums import SourceType


@pytest.fixture(autouse=True)
def _board_cache_is_offline(monkeypatch):
    """Keep the unit tests off Redis.

    Both the negative board cache and the rotation memory are Redis reads on
    every discovered board; these tests are about discovery/parsing, and CI
    (and a bare checkout) may have no Redis at all. Tests that exercise either
    one patch these functions again.
    """
    import scrapers.discovery as discovery

    monkeypatch.setattr(discovery, "board_miss_active", lambda url: False)
    monkeypatch.setattr(discovery, "board_miss_mark", lambda url, **kwargs: None)
    monkeypatch.setattr(discovery, "board_miss_clear", lambda url: None)
    monkeypatch.setattr(discovery, "board_last_seen", lambda source_id, url: None)
    monkeypatch.setattr(
        discovery, "board_mark_seen", lambda source_id, url, **kwargs: None
    )
    monkeypatch.setattr(discovery, "board_forget", lambda source_id, url: None)


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

# RemoteYeah detail pages expose the full JobPosting as JSON-LD but omit `url`
# and `@id`; `skills` is a comma-separated string rather than an array.
REMOTEYEAH_DETAIL_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "JobPosting",
  "title": "Remote Rust Developer Advocate",
  "hiringOrganization": {"@type": "Organization", "name": "SerpApi"},
  "datePosted": "2026-10-16T00:35:39+00:00",
  "description": "<p>Build Rust tooling and demos.</p>",
  "skills": "GitHub, Figma, Rust"
}
</script>
</head><body><h1>Remote Rust Developer Advocate</h1></body></html>
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

# Board-shaped feeds (We Work Remotely) put the employer in each title and use
# categories for region/contract type; the channel title is the board name.
RSS_BOARD_SHAPED_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>We Work Remotely</title>
    <link>https://weworkremotely.com/remote-jobs.rss</link>
    <item>
      <title>Acme Corp: Senior Rust Engineer</title>
      <link>https://weworkremotely.com/jobs/1</link>
      <pubDate>Fri, 01 Aug 2026 10:00:00 GMT</pubDate>
      <description><![CDATA[<p>Build and ship Rust services.</p>]]></description>
      <category>Remote</category>
      <category>Full-Time</category>
      <region>Americas</region>
      <guid>wwr-1</guid>
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
    # schema.org's `jobLocation` is the canonical location, not a tag.
    assert first.location is None


def test_career_page_extracts_json_ld_job_location():
    """`jobLocation` (PostalAddress, list, telecommute) becomes RawJob.location."""
    html = """
    <html><head><script type="application/ld+json">
    [{
      "@type": "JobPosting",
      "title": "Backend Engineer",
      "hiringOrganization": {"name": "Acme"},
      "url": "https://acme.example/jobs/1",
      "jobLocation": [
        {"@type": "Place", "address": {
          "@type": "PostalAddress",
          "addressLocality": "São Paulo",
          "addressRegion": "SP",
          "addressCountry": {"@type": "Country", "name": "BR"}
        }},
        {"@type": "Place", "address": {"addressLocality": "Remote"}}
      ]
    }, {
      "@type": "JobPosting",
      "title": "Designer",
      "hiringOrganization": {"name": "Acme"},
      "url": "https://acme.example/jobs/2",
      "jobLocationType": "TELECOMMUTE",
      "applicantLocationRequirements": {"@type": "Country", "name": "Brazil"}
    }]
    </script></head><body></body></html>
    """
    jobs = CareerPageScraper().parse(_page(html))

    assert jobs[0].location == "São Paulo, SP, BR, Remote"
    # TELECOMMUTE without an address is Remote; the eligible country is the
    # fallback for boards that only say who may apply.
    assert jobs[1].location == "Remote"


def test_location_allowed_keeps_unknown_and_matches_accents():
    """The gate keeps jobs with no location and ignores case/accents."""
    assert location_allowed(None, ["brazil"]) is True
    assert location_allowed("", ["brazil"]) is True
    assert location_allowed("Remote - Brazil", ["brazil"]) is True
    assert location_allowed("São Paulo, SP", ["sao paulo"]) is True
    assert location_allowed("São Paulo, SP", ["SAO PAULO"]) is True
    assert location_allowed("Lisbon, Portugal", ["brazil", "portugal"]) is True
    assert location_allowed("Lisbon, Portugal", ["brazil"]) is False
    # A term must match as a whole word: "us" is not Australia.
    assert location_allowed("Sydney, Australia", ["us"]) is False
    # No configured terms disables the gate entirely.
    assert location_allowed("Lisbon, Portugal", []) is True
    assert location_allowed("Lisbon, Portugal", " , ") is True
    # A comma-separated string is accepted (how the Sources form stores it
    # before the API normalizes it).
    assert location_allowed("Remote, Brazil", "Portugal, Brazil") is True


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


def test_rss_board_flags_split_company_and_enrich_tags():
    scraper = RSSScraper(
        {
            "company_from_title": True,
            "include_region": True,
            "strip_html": True,
        }
    )
    raw = scraper.parse(_page(RSS_BOARD_SHAPED_FEED))

    assert len(raw) == 1
    assert raw[0].title == "Senior Rust Engineer"
    assert raw[0].company == "Acme Corp"
    assert raw[0].description == "Build and ship Rust services."
    # Only the region-like category and the explicit <region> are kept.
    assert raw[0].tags == ["Remote", "Americas"]
    assert raw[0].location == "Americas, Remote"


def test_rss_include_categories_keeps_every_feed_category():
    scraper = RSSScraper({"include_categories": True})
    raw = scraper.parse(_page(RSS_BOARD_SHAPED_FEED))

    assert raw[0].tags == ["Remote", "Full-Time"]


def test_rss_company_from_author_strips_jobspresso_location():
    feed = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Jobs - Jobspresso</title>
      <item>
        <title>Senior Rust Engineer</title>
        <link>https://jobspresso.co/job/senior-rust-engineer/</link>
        <author>Algolia&lt;br&gt;⚲&amp;nbsp;United States</author>
      </item>
    </channel></rss>
    """
    scraper = RSSScraper({"company_from_author": True})
    raw = scraper.parse(_page(feed))
    assert raw[0].title == "Senior Rust Engineer"
    assert raw[0].company == "Algolia"
    # The reading the author suffix carried is still a location.
    assert raw[0].location == "United States"


def test_rss_company_from_title_at_splits_last_company_marker():
    feed = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Remote Jobs on NoDesk</title>
      <item>
        <title>Business Development Representative | UK | Remote at Zipchat AI</title>
        <link>https://nodesk.co/remote-jobs/zipchat-ai-business-development/</link>
      </item>
    </channel></rss>
    """
    scraper = RSSScraper({"company_from_title_at": True})
    raw = scraper.parse(_page(feed))
    assert raw[0].title == "Business Development Representative | UK | Remote"
    assert raw[0].company == "Zipchat AI"


def test_rss_registry_passes_source_config():
    source = SimpleNamespace(type=SourceType.rss, config={"company_from_title": True})
    scraper = get_scraper(source)
    assert isinstance(scraper, RSSScraper)
    assert scraper.config == {"company_from_title": True}


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
    assert raw[0].location == "Remote"
    assert raw[1].title == "Data Scientist"
    assert raw[1].url == "https://board.example/jobs/2"
    assert raw[1].description is None
    assert raw[1].location is None


def test_aggregator_discover_urls_applies_exclude_pattern():
    """Detail mode must not fetch cards the list parser would drop."""
    html = """
    <html><body>
      <article class="job"><a href="/jobs/1">Fresh Rust role</a></article>
      <article class="job"><a href="/jobs/2">Old role</a>
        <span class="status">Vaga expirada</span></article>
    </body></html>
    """
    scraper = GenericHtmlListScraper(
        {
            "detail": True,
            "item_selector": "article.job",
            "url_selector": "a",
            "exclude_pattern": r"\bexpirada\b",
        }
    )
    assert scraper.discover_urls(
        _aggregator_page(html, "https://programathor.com.br/jobs")
    ) == ["https://programathor.com.br/jobs/1"]


def test_aggregator_exclude_pattern_drops_stale_cards():
    html = """
    <html><body>
      <article class="job"><a href="/jobs/1">Fresh Rust role</a></article>
      <article class="job"><a href="/jobs/2">Old role</a>
        <span class="status">Vaga expirada</span></article>
    </body></html>
    """
    scraper = GenericHtmlListScraper(
        {
            "item_selector": "article.job",
            "title_selector": "a",
            "url_selector": "a",
            "exclude_pattern": r"\bexpirada\b",
        }
    )
    raw = scraper.parse(_aggregator_page(html, "https://programathor.com.br/jobs"))
    assert [job.title for job in raw] == ["Fresh Rust role"]


def test_aggregator_reports_a_bad_exclude_pattern():
    scraper = GenericHtmlListScraper(
        {"item_selector": "article", "exclude_pattern": "(["}
    )
    with pytest.raises(ValueError, match="exclude_pattern"):
        scraper.parse(_aggregator_page(AGGREGATOR_HTML))


def test_embedded_json_exclude_pattern_filters_items():
    scraper = EmbeddedJsonListScraper(
        {
            "items_path": "props.pageProps.jobs",
            "title_path": "title",
            "url_path": "slug",
            "company_path": "company.name",
            "exclude_pattern": "nuxt",
        }
    )
    raw = scraper.parse(_aggregator_page(NEXT_DATA_HTML))
    assert [job.title for job in raw] == ["Next.js Engineer"]


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
    assert raw[0].location == "Remote, Brazil"


def test_aggregator_detail_mode_uses_card_location_when_detail_omits_it():
    """A detail page with no location keeps the one printed on its card.

    ``location_selector`` used to be read only in list mode, so ``detail:true``
    boards (Nerdin, Dev.pro, Geekhunter, …) stored every job with no location
    even though the listing printed it.
    """
    listing = """
    <html><body>
      <article class="job">
        <a href="/jobs/1">Staff Platform Engineer</a>
        <span class="location">Remote, Brazil</span>
      </article>
    </body></html>
    """
    detail = """
    <html><body>
      <h1 class="job-title">Staff Platform Engineer</h1>
      <div class="company">Acme</div>
      <div class="job-description">Own the platform.</div>
    </body></html>
    """
    scraper = GenericHtmlListScraper(
        {
            "detail": True,
            "item_selector": "article.job",
            "url_selector": "a",
            "location_selector": ".location",
            "detail_title_selector": "h1.job-title",
            "detail_company_selector": ".company",
            "detail_description_selector": ".job-description",
        }
    )
    detail_url = "https://board.example/jobs/1"
    assert scraper.discover_urls(_aggregator_page(listing)) == [detail_url]

    raw = scraper.parse(_aggregator_page(detail, detail_url))

    assert len(raw) == 1
    assert raw[0].location == "Remote, Brazil"
    # The detail page's own location still wins when it has one.
    raw_with_location = scraper.parse(
        _aggregator_page(
            detail.replace(
                '<div class="company">Acme</div>',
                '<div class="company">Acme</div><div class="location">Lisbon</div>',
            ),
            detail_url,
        )
    )
    assert raw_with_location[0].location == "Lisbon"


def test_aggregator_detail_mode_prefers_json_ld():
    scraper = GenericHtmlListScraper({"detail": True})
    raw = scraper.parse(_aggregator_page(CAREER_PAGE_HTML))
    assert [job.title for job in raw] == ["Senior Python Engineer", "DevOps Engineer"]


def test_aggregator_detail_mode_fills_missing_json_ld_url_from_page():
    """A JobPosting without `url` keeps the detail page URL and its full data."""
    detail_url = "https://remoteyeah.com/jobs/remote-rust-developer-advocate-serpapi"
    scraper = GenericHtmlListScraper({"detail": True})
    raw = scraper.parse(_aggregator_page(REMOTEYEAH_DETAIL_HTML, detail_url))

    assert len(raw) == 1
    assert raw[0].title == "Remote Rust Developer Advocate"
    assert raw[0].company == "SerpApi"
    assert raw[0].url == detail_url
    assert raw[0].posted_date == date(2026, 10, 16)
    assert raw[0].tags == ["GitHub", "Figma", "Rust"]
    assert "Build Rust tooling and demos." in raw[0].description

    normalized = scraper.normalize(raw)
    assert len(normalized) == 1
    assert normalized[0]["url"] == detail_url
    assert normalized[0]["company"] == "SerpApi"
    assert normalized[0]["tags"] == ["GitHub", "Figma", "Rust"]
    assert "Build Rust tooling and demos." in normalized[0]["description"]


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
    def __init__(self, text: str, status_code: int = 200):
        self.status_code = status_code
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


def test_robots_4xx_means_no_restrictions(monkeypatch):
    """RFC 9309: an unavailable robots.txt (4xx) does not block fetching."""
    monkeypatch.setattr(
        utils.httpx, "get", lambda *a, **k: _FakeRobotsResponse("", status_code=404)
    )
    utils._robots_parser_cache.clear()

    decision = utils.robots_decision("https://example.com/jobs/1")

    assert decision.allowed is True
    assert decision.reason == "allowed"
    assert decision.status_code == 404


def test_robots_fetch_failure_is_unavailable_not_a_disallow(monkeypatch):
    """A timeout must not be reported as ``Disallow`` (the Dev.pro regression)."""
    calls: list[int] = []

    def boom(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("dns down")

    monkeypatch.setattr(utils.httpx, "get", boom)
    utils._robots_parser_cache.clear()

    decision = utils.robots_decision("https://dev.pro/jobs")

    assert decision.allowed is False
    assert decision.reason == "unavailable"
    assert "dns down" in (decision.error or "")
    # Retried once with a browser-like user agent before giving up.
    assert len(calls) == 2


def test_robots_failure_is_cached_briefly(monkeypatch):
    """A failed fetch is cached for ~60 s, not the 1 h success TTL."""
    monkeypatch.setattr(
        utils.httpx, "get", lambda *a, **k: _FakeRobotsResponse("", status_code=503)
    )
    utils._robots_parser_cache.clear()

    utils.robots_decision("https://example.com/jobs/1")
    entry = utils._robots_parser_cache["example.com"]

    assert entry.parser is None
    assert entry.ttl == utils._ROBOTS_FAILURE_TTL_SECONDS
    assert entry.ttl < utils._ROBOTS_CACHE_TTL_SECONDS


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


def test_json_ld_identifier_that_names_the_employer_is_not_a_posting_id():
    """Radartec's JSON-LD puts the *employer* id in `identifier`.

    Every ad the board posts itself carries `value: "1"`, so using it as the
    posting id made 18 distinct jobs collide on `uq_jobs_source_external_id`
    (the whole insert was rolled back and reported as skipped). A `name` that
    matches the hiring organization marks the value as an org id.
    """
    html = """
    <script type="application/ld+json">
    {"@type": "JobPosting", "title": "T", "url": "https://x.example/1",
     "hiringOrganization": {"@type": "Organization", "name": "Radartec"},
     "identifier": {"@type": "PropertyValue", "name": "Radartec", "value": "1"}}
    </script>
    """
    jobs = parse_json_ld_jobs(html)
    assert jobs[0].external_id is None


def test_json_ld_identifier_from_another_employer_still_carries_an_id():
    """A `name` that is *not* the hiring org keeps the id (agency-posted ads)."""
    html = """
    <script type="application/ld+json">
    {"@type": "JobPosting", "title": "T", "url": "https://x.example/2",
     "hiringOrganization": {"@type": "Organization", "name": "Radartec"},
     "identifier": {"@type": "PropertyValue", "name": "Sempre IT", "value": "1221"}}
    </script>
    """
    jobs = parse_json_ld_jobs(html)
    assert jobs[0].external_id == "1221"


def test_json_ld_tolerates_control_characters_graph_and_list_type():
    """Real boards emit raw newlines inside strings and wrap nodes in @graph."""
    html = """
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@graph": [
        {"@type": "Organization", "name": "Acme"},
        {"@type": ["JobPosting", "Thing"],
         "title": "Rust Engineer",
         "hiringOrganization": {"@type": "Organization", "name": "Acme"},
         "datePosted": "2026-10-16",
         "url": "https://acme.example/jobs/1",
         "description": "First line
    second line"}
      ]
    }
    </script>
    """
    jobs = parse_json_ld_jobs(html)
    assert len(jobs) == 1
    assert jobs[0].title == "Rust Engineer"
    assert jobs[0].company == "Acme"
    assert jobs[0].posted_date == date(2026, 10, 16)
    assert "second line" in jobs[0].description


def test_json_ld_falls_back_to_page_url_and_splits_skills():
    """Missing `url`/`@id` must not drop the job; a `skills` string is split."""
    page_url = "https://remoteyeah.com/jobs/remote-rust-developer-advocate-serpapi"
    jobs = parse_json_ld_jobs(REMOTEYEAH_DETAIL_HTML, fallback_url=page_url)

    assert len(jobs) == 1
    assert jobs[0].url == page_url
    assert jobs[0].posted_date == date(2026, 10, 16)
    assert jobs[0].tags == ["GitHub", "Figma", "Rust"]
    assert "Build Rust tooling and demos." in jobs[0].description

    # An explicit URL in the JSON-LD still wins over the fallback.
    explicit = parse_json_ld_jobs(CAREER_PAGE_HTML, fallback_url=page_url)
    assert explicit[0].url == "https://acme.example/jobs/42"


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


def test_resolve_path_values_projects_wildcards_and_scalars():
    payload = {
        "jobTags": [
            {"tag": {"name": "CLT"}},
            {"tag": {"name": "100% Remoto"}},
        ],
        "company": {"name": "Acme"},
        "items": [{"id": 1}, {"id": 2}],
    }
    assert resolve_path_values(payload, "jobTags[].tag.name") == [
        "CLT",
        "100% Remoto",
    ]
    assert resolve_path_values(payload, "items[].id") == [1, 2]
    # No wildcard: one value, or an empty list on a miss.
    assert resolve_path_values(payload, "company.name") == ["Acme"]
    assert resolve_path_values(payload, "company.missing") == []
    assert resolve_path_values(payload, "jobTags[].missing") == []
    assert resolve_path_values(payload, "") == [payload]


def test_render_path_template_composes_labels_and_optional_parts():
    item = {
        "type": "remote",
        "city": "São Paulo",
        "state": "SP",
        "country": {"name": None},
        "id": 7,
    }
    labels = {"type": {"remote": "Remote", "hybrid": "Hybrid"}}
    assert render_path_template(
        "{type} - {city}, {state}, {country.name}", item, labels=labels
    ) == "Remote - São Paulo, SP, "
    # A required placeholder (`missing=None`) makes the whole template unresolved.
    assert (
        render_path_template(
            "https://board.example/{id}/{missing}", item, missing=None
        )
        is None
    )
    assert render_path_template("https://board.example/{id}", item, missing=None) == (
        "https://board.example/7"
    )
    # `extra` wins over an item field of the same name.
    assert render_path_template(
        "https://board.example/{url}", item, extra={"url": "https://a.example/1"}
    ) == "https://board.example/https://a.example/1"
    assert render_path_template(None, item) is None


def test_coerce_date_handles_iso_epoch_and_invalid_values():
    assert coerce_date("2026-08-01T10:00:00Z") == date(2026, 8, 1)
    assert coerce_date("2026-08-01") == date(2026, 8, 1)
    assert coerce_date(date(2026, 8, 2)) == date(2026, 8, 2)
    assert coerce_date(datetime(2026, 8, 3, 5, 30)) == date(2026, 8, 3)
    assert coerce_date(1754042400) == date(2025, 8, 1)
    # Lever dates postings with epoch milliseconds; truncating them to a string
    # is what used to break the ATS sweep's batch insert.
    assert coerce_date(1785578400000) == date(2026, 8, 1)
    assert coerce_date(1785578400000.5) == date(2026, 8, 1)
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
            "departments": [{"id": 7, "name": "Engineering"}],
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


def _json_page(payload: object) -> ScrapedPage:
    return ScrapedPage(
        html_content=json.dumps(payload),
        status_code=200,
        final_url="https://api.example",
    )


def test_greenhouse_provider_parses_jobs():
    provider = GreenhouseProvider({"board_token": "acme", "company": "Acme"})
    # `?content=true` is what makes the payload carry each posting's body.
    assert provider.results_url() == (
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
    )
    jobs = provider.parse(_json_page(GREENHOUSE_PAYLOAD))
    assert len(jobs) == 1
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].url == "https://boards.greenhouse.io/acme/jobs/1"
    assert jobs[0].company == "Acme"
    assert "Build APIs" in jobs[0].description
    # The same text feeds the local filters; `description` is what gets stored.
    assert jobs[0].match_text == jobs[0].description
    # Greenhouse departments are ``{id, name}``, unlike SmartRecruiters' labels.
    assert jobs[0].tags == ["Remote, Brazil", "Engineering"]
    assert jobs[0].location == "Remote, Brazil"
    assert jobs[0].posted_date == date(2026, 8, 1)


def test_greenhouse_prefers_first_published_over_updated_at():
    """`updated_at` moves on every edit, so it is not the posting date."""
    provider = GreenhouseProvider({"board_token": "acme"})
    payload = {
        "jobs": [
            {
                "id": 1,
                "title": "Backend Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                "first_published": "2026-08-01T10:00:00-04:00",
                "updated_at": "2026-09-30T10:00:00Z",
            },
            {
                "id": 2,
                "title": "Data Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/2",
                "updated_at": "2026-09-30T10:00:00Z",
            },
        ]
    }

    jobs = provider.parse(_json_page(payload))

    assert jobs[0].posted_date == date(2026, 8, 1)
    # Boards that predate `first_published` still get a date.
    assert jobs[1].posted_date == date(2026, 9, 30)


async def test_greenhouse_falls_back_to_the_listing_without_content(monkeypatch):
    """A host refusing `content=true` must not cost the sweep the board."""
    import scrapers.discovery as discovery

    seen: list[str] = []

    async def fake_fetch_html(url, *, auth=None, max_bytes=None):
        seen.append(url)
        if "content=true" in url:
            raise httpx.HTTPStatusError(
                "400", request=httpx.Request("GET", url), response=httpx.Response(400)
            )
        return ScrapedPage(
            html_content=json.dumps(GREENHOUSE_PAYLOAD), status_code=200, final_url=url
        )

    monkeypatch.setattr(discovery, "fetch_html", fake_fetch_html)
    provider = GreenhouseProvider({"board_token": "acme"})
    url = provider.results_url()

    page = await provider.fetch(url)

    assert seen == [url, "https://boards-api.greenhouse.io/v1/boards/acme/jobs"]
    # The sweep finds its parser by the URL it registered, so the fallback page
    # has to keep that URL.
    assert page.final_url == url
    assert [job.title for job in provider.parse(page)] == ["Backend Engineer"]


def test_greenhouse_matches_keywords_past_the_stored_description_limit():
    """The tech stack usually sits far past the 2 KB the app stores."""
    scraper = DiscoveryScraper(
        "brave",
        {"query": "rust", "sweep_ats": True, "keywords": ["rust"]},
    )
    board = resolve_ats_board("https://boards.greenhouse.io/acme/jobs/1")
    assert board is not None
    board_url = scraper._register_board(board)
    body = "<p>" + ("Filler sentence. " * 300) + "We build with Rust.</p>"
    payload = {
        "jobs": [
            {
                "id": 1,
                "title": "Backend Engineer",
                "location": {"name": "Remote, Brazil"},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                "content": body,
            }
        ]
    }
    page = ScrapedPage(
        html_content=json.dumps(payload), status_code=200, final_url=board_url
    )

    kept = scraper.parse(page)

    assert [job.external_id for job in kept] == ["1"]
    # Matched on the whole body, but only the first 2 KB is stored.
    assert len(kept[0].description) == 2000
    assert "Rust" not in kept[0].description


ATS_DATE_PAYLOADS = [
    pytest.param(
        AshbyProvider({"org": "acme", "company": "Acme"}),
        {
            "jobs": [
                {
                    "id": "1",
                    "title": "Backend Engineer",
                    "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                    "publishedAt": "2026-08-01T10:00:00.000+00:00",
                }
            ]
        },
        date(2026, 8, 1),
        id="ashby",
    ),
    pytest.param(
        GreenhouseProvider({"board_token": "acme", "company": "Acme"}),
        {
            "jobs": [
                {
                    "id": 1,
                    "title": "Backend Engineer",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                    "updated_at": "2026-08-01T10:00:00Z",
                }
            ]
        },
        date(2026, 8, 1),
        id="greenhouse",
    ),
    pytest.param(
        LeverProvider({"company": "acme"}),
        [
            {
                "id": "1",
                "text": "Backend Engineer",
                "hostedUrl": "https://jobs.lever.co/acme/1",
                "createdAt": 1785578400000,  # epoch milliseconds
            }
        ],
        date(2026, 8, 1),
        id="lever-epoch-ms",
    ),
    pytest.param(
        WorkableProvider({"org": "acme", "company": "Acme"}),
        {
            "jobs": [
                {
                    "title": "Backend Engineer",
                    "url": "https://apply.workable.com/acme/j/1",
                    "published_on": "2026-08-01",
                }
            ]
        },
        date(2026, 8, 1),
        id="workable",
    ),
]


@pytest.mark.parametrize("provider, payload, expected", ATS_DATE_PAYLOADS)
def test_ats_providers_emit_date_objects_for_posted_date(provider, payload, expected):
    """``posted_date`` must be a ``date`` — asyncpg rejects a str for DATE.

    Regression: the ATS sweep used to keep the ``YYYY-MM-DD`` slice of the
    payload timestamp, which failed the run's whole batch insert.
    """
    jobs = provider.parse(_json_page(payload))

    assert len(jobs) == 1
    assert jobs[0].posted_date == expected
    assert isinstance(jobs[0].posted_date, date)


def test_ats_provider_missing_config_raises():
    with pytest.raises(ValueError):
        GreenhouseProvider({}).results_url()


def test_ats_board_resolver_recognises_public_job_urls():
    """A search result is enough to identify a board; site chrome is not."""
    assert resolve_ats_board("https://jobs.ashbyhq.com/acme/123").config == {
        "org": "acme",
        "company": "acme",
    }
    assert resolve_ats_board("https://jobs.lever.co/Acme/abc").config == {
        "company": "Acme",
        "limit": 100,
    }
    assert resolve_ats_board("https://jobs.eu.lever.co/acme/abc").config["api_host"] == (
        "api.eu.lever.co"
    )
    assert resolve_ats_board("https://boards.greenhouse.io/acme/jobs/1").config == {
        "board_token": "acme",
        "company": "acme",
    }
    assert resolve_ats_board("https://job-boards.eu.greenhouse.io/acme/jobs/1").config[
        "api_host"
    ] == "boards.eu.greenhouse.io"
    assert resolve_ats_board("https://jobs.smartrecruiters.com/Acme/123").config == {
        "company": "Acme"
    }

    # Board-host roots, ATS chrome paths and unrelated sites are not boards.
    assert resolve_ats_board("https://jobs.ashbyhq.com/") is None
    assert resolve_ats_board("https://boards.greenhouse.io/jobs/1") is None
    assert resolve_ats_board("https://example.com/acme/jobs/1") is None
    assert resolve_ats_board("ftp://jobs.lever.co/acme/1") is None


def test_eu_board_hosts_and_lever_limit_are_honoured():
    # Greenhouse serves its EU API from the very host of the EU job board;
    # `boards-api.eu.greenhouse.io` does not resolve at all.
    assert (
        GreenhouseProvider(
            {"board_token": "acme", "api_host": "boards.eu.greenhouse.io"}
        ).results_url()
        == "https://boards.eu.greenhouse.io/v1/boards/acme/jobs?content=true"
    )
    # A board is read page by page, so the page size is always in the URL: a
    # 715-posting Lever board used to be read as its first 100 postings.
    assert (
        LeverProvider({"company": "acme"}).results_url()
        == "https://api.lever.co/v0/postings/acme?mode=json&limit=100"
    )
    pager = LeverProvider({"company": "acme", "limit": 50})
    assert pager.results_url() == "https://api.lever.co/v0/postings/acme?mode=json&limit=50"
    # `skip` walks the board; the first page carries no cursor at all.
    assert pager._page_url(pager.results_url(), 0) == (
        "https://api.lever.co/v0/postings/acme?mode=json&limit=50"
    )
    assert pager._page_url(pager.results_url(), 50) == (
        "https://api.lever.co/v0/postings/acme?mode=json&limit=50&skip=50"
    )


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

#: FullStack Talent's public board: ids only, a `hasNextPage` flag and a
#: URL-encoded filter. This is the config documented in docs/scraping.md.
FULLSTACK_URL = (
    "https://api-v1.fullstack.com/api/job-postings/public"
    "?page={page}&take=30&filter=regionGroup%3DLatam"
)
FULLSTACK_CONFIG = {
    "provider": "json_list",
    "url_tpl": FULLSTACK_URL,
    "max_pages": 200,
    "next_page_path": "meta.hasNextPage",
    "items_path": "data",
    "id_path": "id",
    "title_path": "jobTitle",
    "company": "FullStack",
    "url_path": "id",
    "job_url_tpl": "https://talent.fullstack.com/jobs/{id}",
    "location_path": "region",
    "date_path": "createdAt",
    "tags_path": "skillsNames",
}
FULLSTACK_PAYLOAD = {
    "data": [
        {
            "id": "6f0b2c1e-8a4d-4c1f-9f6e-2b1d0c3a4e5f",
            "jobTitle": "Senior Backend Engineer",
            "region": "Brazil",
            "regionGroup": "Latam",
            "city": "São Paulo",
            "createdAt": "2026-10-01T12:00:00.000Z",
            "skillsNames": ["Python", "AWS"],
        },
        # A posting without a title cannot be stored, so it is skipped.
        {"id": "a1b2c3d4", "region": "Argentina", "createdAt": None},
    ],
    "meta": {"page": 1, "take": 30, "pageCount": 82, "hasNextPage": True},
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
    assert first.location == "Remote, Brazil"
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


def test_json_list_provider_renders_job_url_tpl_from_item_fields():
    """`job_url_tpl` turns an id/slug into the public posting URL."""
    provider = JsonListProvider(
        {
            "url": "https://api.example/jobs",
            "items_path": "data",
            "id_path": "id",
            "title_path": "title",
            "url_path": "id",
            "job_url_tpl": "https://board.example/jobs/{id}",
        }
    )
    assert provider.results_url() == "https://api.example/jobs"
    jobs = provider.parse(_json_page({"data": [{"id": "abc", "title": "Dev"}]}))
    # Without the template the id would have resolved against the API host.
    assert jobs[0].url == "https://board.example/jobs/abc"
    assert jobs[0].external_id == "abc"

    slugged = JsonListProvider(
        {
            "url": "https://api.example/jobs",
            "items_path": "data",
            "title_path": "title",
            "url_path": "slug",
            "job_url_tpl": "https://{lang}.board.example/{url}",
        }
    )
    page = _json_page({"data": [{"slug": "dev", "title": "Dev", "lang": "br"}]})
    assert slugged.parse(page)[0].url == "https://br.board.example/dev"


def test_json_list_provider_rejects_a_bad_job_url_tpl():
    provider = JsonListProvider(
        {
            "url": "https://api.example/jobs",
            "items_path": "data",
            "title_path": "title",
            "url_path": "id",
            "job_url_tpl": "https://board.example/jobs/{nope}",
        }
    )
    with pytest.raises(ValueError, match="job_url_tpl"):
        provider.parse(_json_page({"data": [{"id": "abc", "title": "Dev"}]}))


def test_json_list_provider_stops_paging_on_next_page_path():
    """The API's own flag ends the walk instead of an empty page after it."""
    provider = JsonListProvider(FULLSTACK_CONFIG)
    more = _json_page({"data": [], "meta": {"hasNextPage": True}})
    assert provider.next_page_url(more) == FULLSTACK_URL.format(page=2)
    # The provider is now on page 2 and the API reports the last page.
    last = _json_page({"data": [], "meta": {"hasNextPage": False}})
    assert provider.next_page_url(last) is None
    # A missing flag means "no more pages", never a broken URL.
    assert provider.next_page_url(_json_page({"data": [], "meta": {}})) is None


def test_fullstack_config_parses_the_public_board():
    JsonListProvider.validate_config(FULLSTACK_CONFIG)
    provider = JsonListProvider(FULLSTACK_CONFIG)
    assert provider.results_url() == FULLSTACK_URL.format(page=1)

    page = _json_page(FULLSTACK_PAYLOAD)
    jobs = provider.parse(page)

    assert [job.title for job in jobs] == ["Senior Backend Engineer"]
    first = jobs[0]
    assert first.company == "FullStack"
    assert first.external_id == "6f0b2c1e-8a4d-4c1f-9f6e-2b1d0c3a4e5f"
    assert first.url == "https://talent.fullstack.com/jobs/6f0b2c1e-8a4d-4c1f-9f6e-2b1d0c3a4e5f"
    assert first.location == "Brazil"
    assert first.posted_date == date(2026, 10, 1)
    assert first.tags == ["Python", "AWS", "Brazil"]
    # The list payload carries no body; descriptions need the detail endpoint.
    assert first.description is None
    assert provider.next_page_url(page) == FULLSTACK_URL.format(page=2)

# --- Remotar (public jobs API) ------------------------------------------------


REMOTAR_CONFIG = {
    "provider": "json_list",
    "url": "https://api.remotar.com.br/jobs?page={page}&limit={page_size}",
    "page_size": 100,
    "max_pages": 200,
    "items_path": "data",
    "id_path": "id",
    "title_path": "title",
    "url_path": "externalLink",
    "url_fallback_tpl": "https://remotar.com.br/job/{id}",
    "company_path": "company.name",
    "location_tpl": "{type} - {city}, {state}, {country.name}",
    "value_labels": {
        "type": {"remote": "Remote", "hybrid": "Hybrid", "onsite": "On-site"},
    },
    "date_path": "createdAt",
    "description_path": "description",
    "tags_paths": ["jobTags[].tag.name", "jobCategories[].category.name"],
    "match_paths": ["subtitle", "description", "jobRequirements[].description"],
    "skip_if_true": ["expired"],
    "skip_if_false": ["active"],
    "last_page_path": "meta.last_page",
    "current_page_path": "meta.current_page",
    "keywords": ["rust", "c++", "cpp", "golang", "go engineer", "go developer"],
    "exclude_keywords": ["sales"],
    "locations": [
        "remote",
        "brazil",
        "brasil",
        "sao paulo",
        "são paulo",
        "sao jose dos campos",
        "são josé dos campos",
    ],
}
REMOTAR_PAYLOAD = {
    "meta": {"total": 10, "per_page": 100, "current_page": 1, "last_page": 2},
    "data": [
        {
            "id": 168020,
            "title": "Senior Go Engineer",
            "subtitle": "GoLang, microsserviços e arquitetura hexagonal",
            "description": "<p>Build <b>APIs</b> in Go.</p>",
            "type": "remote",
            "city": "São Paulo",
            "state": "SP",
            "country": None,
            "externalLink": "https://quality.example/jobs/168020",
            "active": True,
            "expired": False,
            "createdAt": "2026-10-23T17:37:36.204-03:00",
            "company": {"name": "Quality Digital"},
            "jobTags": [{"tag": {"name": "CLT"}}, {"tag": {"name": "100% Remoto"}}],
            "jobCategories": [{"category": {"name": "Programação"}}],
            "jobRequirements": [{"description": "Experiência com Rust e C++."}],
        },
        {
            "id": 168021,
            "title": "Platform Engineer",
            "subtitle": "Python and Django",
            "description": "<p>Own the platform.</p>",
            "type": "remote",
            "city": "",
            "state": "",
            "country": None,
            "externalLink": None,
            "active": True,
            "expired": False,
            "createdAt": "2026-10-22T10:00:00-03:00",
            "company": {"name": "Acme"},
            "jobTags": [],
            "jobCategories": [],
            "jobRequirements": [{"description": "Rust in production."}],
        },
        {
            "id": 168022,
            "title": "Python Developer",
            "subtitle": "Django",
            "description": "<p>Python only.</p>",
            "type": "remote",
            "externalLink": "https://example.test/168022",
            "active": True,
            "expired": False,
            "company": {"name": "Beta"},
            "jobRequirements": [],
        },
        {
            "id": 168023,
            "title": "Rust Engineer",
            "subtitle": "Sistemas distribuídos",
            "description": "<p>Rust and Tokio.</p>",
            "type": "hybrid",
            "city": "São Paulo",
            "state": "SP",
            "country": {"name": "Brasil"},
            "externalLink": "https://example.test/168023",
            "active": True,
            "expired": False,
            "createdAt": "2026-10-21T09:00:00-03:00",
            "company": {"name": "Gamma"},
            "jobRequirements": [],
        },
        {
            "id": 168024,
            "title": "C++ Developer",
            "description": "<p>C++ and Qt.</p>",
            "type": "onsite",
            "city": "Rio de Janeiro",
            "state": "RJ",
            "externalLink": "https://example.test/168024",
            "active": True,
            "expired": False,
            "company": {"name": "Delta"},
        },
        {
            "id": 168025,
            "title": "Expired Rust Developer",
            "description": "<p>Rust.</p>",
            "type": "remote",
            "active": True,
            "expired": True,
            "externalLink": "https://example.test/168025",
        },
        {
            "id": 168026,
            "title": "Inactive Rust Developer",
            "description": "<p>Rust.</p>",
            "type": "remote",
            "active": False,
            "expired": False,
            "externalLink": "https://example.test/168026",
        },
        {
            "id": 168027,
            "title": "Go Developer",
            "description": "<p>Go services.</p>",
            "type": "onsite",
            "city": "São José dos Campos",
            "state": "SP",
            "externalLink": "https://example.test/168027",
            "active": True,
            "expired": False,
            "company": {"name": "Epsilon"},
        },
        {
            "id": 168028,
            "description": "<p>Rust without a title.</p>",
            "type": "remote",
            "externalLink": "https://example.test/168028",
            "active": True,
            "expired": False,
        },
        {
            "id": 168029,
            "title": "Rust Sales Engineer",
            "description": "<p>Rust demos.</p>",
            "type": "remote",
            "externalLink": "https://example.test/168029",
            "active": True,
            "expired": False,
            "company": {"name": "Zeta"},
        },
    ],
}


def test_remotar_config_maps_the_public_api_payload():
    provider = JsonListProvider(REMOTAR_CONFIG)

    assert provider.results_url() == (
        "https://api.remotar.com.br/jobs?page=1&limit=100"
    )
    assert provider.page_size() == 100
    assert provider.max_pages() == 200

    jobs = provider.parse(_json_page(REMOTAR_PAYLOAD))

    # The provider maps; filtering is the DiscoveryScraper's job (see the next
    # test). Expired/inactive rows and rows without a title are skipped here.
    assert [job.title for job in jobs] == [
        "Senior Go Engineer",
        "Platform Engineer",
        "Python Developer",
        "Rust Engineer",
        "C++ Developer",
        "Go Developer",
        "Rust Sales Engineer",
    ]
    first = jobs[0]
    assert first.company == "Quality Digital"
    assert first.external_id == "168020"
    assert first.url == "https://quality.example/jobs/168020"
    assert first.posted_date == date(2026, 10, 23)
    assert first.location == "Remote - São Paulo, SP"
    assert first.tags == [
        "CLT",
        "100% Remoto",
        "Programação",
        "Remote - São Paulo, SP",
    ]
    assert first.description is not None
    assert "Build" in first.description and "<b>" not in first.description
    # The keyword gate sees the subtitle, the body and the requirements.
    assert first.match_text is not None
    assert "GoLang" in first.match_text
    assert "Rust e C++" in first.match_text

    # `externalLink` is absent on some rows: the public posting URL is rebuilt.
    assert jobs[1].url == "https://remotar.com.br/job/168021"
    assert jobs[1].location == "Remote"
    # A hybrid posting keeps its city/state/country label.
    assert jobs[3].location == "Hybrid - São Paulo, SP, Brasil"
    assert jobs[5].location == "On-site - São José dos Campos, SP"


def test_remotar_config_uses_the_generic_discovery_filters():
    """A plain json_list source gets keywords/locations without custom Python."""

    scraper = DiscoveryScraper("json_list", REMOTAR_CONFIG)
    jobs = scraper.parse(_json_page(REMOTAR_PAYLOAD))

    assert [job.title for job in jobs] == [
        "Senior Go Engineer",
        "Platform Engineer",
        "Rust Engineer",
        "Go Developer",
    ]
    assert scraper.allow_empty is True
    assert scraper._location_dropped == 1  # C++ role in Rio de Janeiro
    assert scraper._location_unknown == 0


def test_remotar_config_follows_the_numeric_last_page():
    provider = JsonListProvider(REMOTAR_CONFIG)
    first = _json_page(
        {
            "data": [],
            "meta": {"current_page": 1, "last_page": 2, "per_page": 100, "total": 150},
        }
    )
    assert provider.next_page_url(first) == (
        "https://api.remotar.com.br/jobs?page=2&limit=100"
    )
    last = _json_page(
        {
            "data": [],
            "meta": {"current_page": 2, "last_page": 2, "per_page": 100, "total": 150},
        }
    )
    assert provider.next_page_url(last) is None
    # `last_page_path` is authoritative: a payload that loses it stops the walk
    # instead of fetching empty pages up to `max_pages`.
    assert provider.next_page_url(_json_page({"data": [], "meta": {}})) is None
    # `current_page_path` wins over the provider's own cursor.
    ahead = _json_page(
        {"data": [], "meta": {"current_page": 3, "last_page": 4, "per_page": 100}}
    )
    assert provider.next_page_url(ahead) == (
        "https://api.remotar.com.br/jobs?page=4&limit=100"
    )
    # The source's own page budget still caps the walk.
    capped = JsonListProvider({**REMOTAR_CONFIG, "max_pages": 1})
    assert capped.next_page_url(first) is None


def test_remotar_config_keyword_gate_respects_whole_terms_and_exclusions():
    scraper = DiscoveryScraper(
        "json_list",
        {
            **REMOTAR_CONFIG,
            "keywords": ["c++", "rust"],
            "exclude_keywords": ["sales"],
            "locations": ["remote"],
        },
    )
    payload = {
        "data": [
            # `c++` has no word boundary at the end; the term matcher handles it.
            {"id": 1, "title": "C++ Developer", "type": "remote"},
            # "Django" must not match the whole term "rust".
            {"id": 2, "title": "Django Developer", "type": "remote"},
            # Exclusion wins over a matching keyword.
            {"id": 3, "title": "Rust Sales Engineer", "type": "remote"},
        ]
    }
    jobs = scraper.parse(_json_page(payload))
    assert [job.title for job in jobs] == ["C++ Developer"]


def test_remotar_config_rejects_a_payload_without_a_job_array():
    provider = JsonListProvider(REMOTAR_CONFIG)
    with pytest.raises(ValueError, match="array"):
        provider.parse(_json_page({"data": "not-a-list"}))


def test_remotar_config_is_registered_and_dispatched():
    provider = get_discovery_provider("json_list", REMOTAR_CONFIG)
    assert isinstance(provider, JsonListProvider)
    assert provider.family == "json"
    assert provider.requires_key is False
    JsonListProvider.validate_config(REMOTAR_CONFIG)
    metadata = JsonListProvider.config_metadata()["optional"]
    for key in (
        "keywords",
        "locations",
        "match_paths",
        "location_tpl",
        "last_page_path",
        "tags_paths",
        "skip_if_true",
        "url_fallback_tpl",
    ):
        assert key in metadata

    scraper = get_scraper(
        SimpleNamespace(type=SourceType.discovery, config=REMOTAR_CONFIG)
    )
    assert scraper.first_fetch_url("https://ignored.example") == (
        "https://api.remotar.com.br/jobs?page=1&limit=100"
    )
    assert scraper.allow_empty is True


def test_remotar_config_owns_the_page_budget_and_page_size():
    assert JsonListProvider(REMOTAR_CONFIG).max_pages() == 200
    assert JsonListProvider({**REMOTAR_CONFIG, "max_pages": 5}).max_pages() == 5
    assert JsonListProvider({"url": "https://api.example/jobs"}).max_pages() == 1
    assert JsonListProvider(REMOTAR_CONFIG).page_size() == 100


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


# --- WordPress admin-ajax boards (form bodies + HTML fragments) ---------------

#: A board whose "load more" action takes a form-encoded POST and answers with
#: HTML *inside* JSON. Pinned to the site's own Latin America view, because the
#: endpoint filters server-side: `locations=["latin-america"]` -> 12 of 57.
SIGMA_CONFIG = {
    "provider": "json_list",
    "url": "https://career.sigma.software/wp-admin/admin-ajax.php",
    "method": "POST",
    "body_encoding": "form",
    "body": {
        "action": "filter_vacancies_v2_loadmore",
        "page": "{page0}",
        "keyword": "",
        "locations": '["latin-america"]',
    },
    "items_path": "data.html",
    "item_selector": "a.vacancy-card-new",
    "title_selector": ".vacancy-card-new__title",
    "location_selector": ".vacancy-card-new__locations span",
    "tags_selector": (
        ".vacancy-card-new__technologies span, .vacancy-card__seniority, .vacancy-card__workplace"
    ),
    "company": "Sigma Software",
    "next_page_path": "data.has_more",
    "max_pages": 8,
    "max_results": 60,
    "keywords": ["rust", "c++", "cpp", "golang", "go engineer", "go developer"],
    "locations": ["latam", "latin america", "brazil", "brasil", "sao paulo", "argentina"],
    "allow_empty": True,
}


def _sigma_card(
    *,
    title: str,
    href: str,
    seniority: str,
    workplace: str,
    locations: str,
    technologies: str,
) -> str:
    """One card, structured like the board's own markup."""
    return (
        f'<a class="vacancy-card-new" href="{href}">'
        f'<h3 class="vacancy-card-new__title">{title}</h3>'
        f'<span class="vacancy-card__seniority">{seniority}</span>'
        f'<span class="vacancy-card__workplace">{workplace}</span>'
        f'<div class="vacancy-card-new__locations"><span>{locations}</span></div>'
        f'<div class="vacancy-card-new__technologies"><span>{technologies}</span></div>'
        "</a>"
    )


SIGMA_PAYLOAD = {
    "success": True,
    "data": {
        "html": "".join(
            [
                _sigma_card(
                    title="Software Architect (AdTech)",
                    href="https://career.sigma.software/vacancy/software-architect-adtech/",
                    seniority="Senior",
                    workplace="Remote",
                    locations="Latin America, Brazil, Colombia",
                    technologies="Software Development, C++, Embedded, Engineering",
                ),
                _sigma_card(
                    title="Middle Data Engineer",
                    href="https://career.sigma.software/vacancy/middle-data-engineer-12/",
                    seniority="Middle",
                    workplace="Remote",
                    locations="Latin America, Argentina, Brazil",
                    technologies="Engineering, Databases, Python",
                ),
                _sigma_card(
                    title="Rust Engineer (Warsaw)",
                    href="https://career.sigma.software/vacancy/rust-engineer-warsaw/",
                    seniority="Senior",
                    workplace="Hybrid",
                    locations="Europe, Poland",
                    technologies="Rust, Embedded",
                ),
                _sigma_card(
                    title="Go Developer",
                    href="https://career.sigma.software/vacancy/go-developer-7/",
                    seniority="Middle",
                    workplace="Remote",
                    locations="Latin America, Argentina",
                    technologies="GO, Golang, Python",
                ),
            ]
        ),
        "has_more": True,
        "total": 4,
    },
}


def test_json_list_sends_a_form_body_with_zero_based_pages():
    provider = JsonListProvider(SIGMA_CONFIG)

    assert provider.body_encoding() == "form"
    # The action's `page` is 0-based: page 1 of the walk asks for 0.
    assert provider.request_spec(provider.results_url())[1]["page"] == "0"
    assert provider.pagination_in_body is True

    # A 1-based `{page}` keeps working for the vendors that expect it.
    jooble = JsonListProvider({"url": "u", "method": "POST", "body": {"page": "{page}"}})
    assert jooble.request_spec("u") == ("POST", {"page": "1"})
    assert jooble.body_encoding() == "json"

    # Body pagination repeats the endpoint, so only the board's own flag ends it.
    next_url = provider.next_page_url(_json_page(SIGMA_PAYLOAD))
    assert next_url == SIGMA_CONFIG["url"]
    assert provider.request_spec(next_url)[1]["page"] == "1"
    assert provider.next_page_url(_json_page({"data": {"html": "", "has_more": False}})) is None

    with pytest.raises(ValueError, match="body_encoding"):
        JsonListProvider({**SIGMA_CONFIG, "body_encoding": "xml"}).body_encoding()


def test_sigma_config_parses_the_html_fragment_into_jobs():
    """`items_path` pointing at a string parses it as a listing page."""
    jobs = JsonListProvider(SIGMA_CONFIG).parse(_json_page(SIGMA_PAYLOAD))

    assert [job.title for job in jobs] == [
        "Software Architect (AdTech)",
        "Middle Data Engineer",
        "Rust Engineer (Warsaw)",
        "Go Developer",
    ]
    first = jobs[0]
    assert first.url == "https://career.sigma.software/vacancy/software-architect-adtech/"
    assert first.company == "Sigma Software"
    assert first.location == "Latin America, Brazil, Colombia"
    # The chips are the only place the stack is printed, and a chip may carry a
    # comma list: every part becomes its own tag, where the keyword gate reads.
    assert first.tags == [
        "Software Development",
        "C++",
        "Embedded",
        "Engineering",
        "Senior",
        "Remote",
    ]
    # Cards carry no date and no body: the listing parser's location line is all
    # the description can be, exactly as for `generic_html_list`.
    assert first.posted_date is None
    assert first.description == "Location: Latin America, Brazil, Colombia"


def test_sigma_config_applies_the_keyword_and_location_gate():
    scraper = DiscoveryScraper("json_list", SIGMA_CONFIG)
    jobs = scraper.parse(_json_page(SIGMA_PAYLOAD))

    assert [job.title for job in jobs] == ["Software Architect (AdTech)", "Go Developer"]
    assert scraper.allow_empty is True
    # Python-only row: dropped by `keywords`. Warsaw row: dropped by `locations`.
    assert scraper._location_dropped == 1
    assert scraper._location_unknown == 0


def test_sigma_config_is_registered_and_dispatched():
    provider = get_discovery_provider("json_list", SIGMA_CONFIG)
    assert provider.requires_key is False
    JsonListProvider.validate_config(SIGMA_CONFIG)
    metadata = JsonListProvider.config_metadata()["optional"]
    for key in ("body_encoding", "item_selector", "title_selector", "tags_selector"):
        assert key in metadata

    scraper = get_scraper(SimpleNamespace(type=SourceType.discovery, config=SIGMA_CONFIG))
    assert scraper.first_fetch_url("https://ignored.example") == SIGMA_CONFIG["url"]
    assert scraper.allow_empty is True


# --- Public JSON boards behind an SPA (Tecla) --------------------------------

#: `app.tecla.io/jobs` is a CRA shell, but its bundle calls an anonymous listing
#: API: 9 rows per page (it ignores `limit`/`page_size`) and 34 postings across
#: 4 pages. The payload reports no location beyond the `usaOnly` residency flag,
#: so the config labels every row `Remote` and treats `usaOnly` as the location
#: filter; the stack lives in `requiredSkills`/`category`, which is what the
#: keyword gate reads.
TECLA_CONFIG = {
    "provider": "json_list",
    "url": "https://api.tecla.io/api/jobs/getPublicJobs/?page={page}",
    "max_pages": 8,
    "last_page_path": "data.pagination.countPages",
    "current_page_path": "data.pagination.current",
    "items_path": "data.jobs",
    "id_path": "id",
    "title_path": "name",
    "url_path": "id",
    "job_url_tpl": "https://app.tecla.io/job?id={id}",
    "company_path": "company.name",
    "location_tpl": "Remote",
    "date_path": "createdAt",
    "description_path": "description",
    "tags_paths": [
        "requiredSkills[].skill.name",
        "category",
        "seniorityName",
        "commitment.name",
    ],
    "match_paths": ["subtitle", "description"],
    "skip_if_true": ["usaOnly"],
    "max_age_days": 90,
    "max_results": 40,
    "keywords": ["rust", "c++", "cpp", "golang", "go engineer", "go developer"],
    "locations": ["remote", "latam", "latin america", "south america", "americas",
                  "brazil", "brasil", "sao paulo", "argentina", "colombia", "mexico"],
    "allow_empty": True,
}


def _tecla_job(
    *,
    job_id: int,
    name: str,
    company: str,
    skills: tuple[str, ...] = (),
    category: str = "Engineering",
    seniority: str = "",
    commitment: str = "Full-Time",
    description: str = "",
    subtitle: str = "",
    city: str = "",
    state: str = "",
    usa_only: bool | None = False,
    age_days: int = 3,
) -> dict:
    """One posting, shaped like `getPublicJobs` (dates relative to today)."""
    created = date.today() - timedelta(days=age_days)
    return {
        "id": job_id,
        "name": name,
        "company": {"name": company, "country": "United States of America"},
        "category": category,
        "seniority": "jr",
        "seniorityName": f"{seniority} {name}".strip(),
        "commitment": {"id": 1, "name": commitment},
        "requiredSkills": [{"skill": {"id": 1, "name": skill}} for skill in skills],
        "createdAt": f"{created.isoformat()}T15:51:27.008372",
        "description": description,
        "subtitle": subtitle,
        "city": city,
        "state": state,
        "usaOnly": usa_only,
    }


TECLA_PAYLOAD = {
    "success": True,
    "data": {
        "jobs": [
            _tecla_job(
                job_id=3411,
                name="HTML5 Ad Developer",
                company="New Engen",
                seniority="Jr.",
                skills=("HTML5", "JavaScript", "CSS3"),
                description=(
                    "Along with our partner, we are seeking a Junior HTML5 Ad "
                    "Developer to focus specifically on the development and "
                    "production of HTML5 digital advertising."
                ),
            ),
            _tecla_job(
                job_id=3412,
                name="Data Scientist (US only)",
                company="Acme",
                category="Data",
                skills=("Data Science", "Machine Learning", "Python"),
                city="Glendale",
                state="California",
                usa_only=True,
            ),
            _tecla_job(
                job_id=3404,
                name="Staff Engineer (AI Infrastructure)",
                company="New Engen",
                seniority="Senior/Staff",
                skills=("Software Development", "Software Engineering", "Automated Testing"),
                subtitle="Senior/Staff Software Engineer, Rust and Python",
            ),
            _tecla_job(
                job_id=3295,
                name="Lead Full-Stack Developer",
                company="BairesDev",
                skills=("SQL", "Python", "React", "TypeScript"),
            ),
            _tecla_job(
                job_id=3500,
                name="Senior Rust Engineer",
                company="Acme LatAm",
                seniority="Senior",
                skills=("Rust", "PostgreSQL", "AWS"),
            ),
            _tecla_job(
                job_id=3501,
                name="Rust Engineer (US only)",
                company="Acme",
                skills=("Rust", "AWS"),
                usa_only=True,
            ),
            _tecla_job(
                job_id=3502,
                name="Backend Developer (Payments)",
                company="Acme LatAm",
                skills=("Python", "Django"),
                description="Our ledger service is written in <b>Rust</b>",
                usa_only=None,
            ),
            _tecla_job(
                job_id=3113,
                name="SAP ABAP Developer",
                company="Acme",
                skills=("SAP ABAP", "SAP FI"),
                age_days=400,
            ),
        ],
        "pagination": {"count": 8, "countPages": 4, "current": 1, "prev": 1, "next": 2},
    },
}


def test_tecla_config_maps_the_public_payload_into_jobs():
    jobs = JsonListProvider(TECLA_CONFIG).parse(_json_page(TECLA_PAYLOAD))

    # `usaOnly` rows are dropped by the provider before any field mapping.
    assert [job.external_id for job in jobs] == [
        "3411",
        "3404",
        "3295",
        "3500",
        "3502",
        "3113",
    ]
    first = jobs[0]
    # The API carries only an id, so `job_url_tpl` builds the public posting link.
    assert first.url == "https://app.tecla.io/job?id=3411"
    assert first.company == "New Engen"
    assert first.posted_date == date.today() - timedelta(days=3)
    # No per-row location exists: the board is a LatAm-remote marketplace, so the
    # config labels it and the location gate stays meaningful (see the next test).
    assert first.location == "Remote"
    assert first.tags == [
        "HTML5",
        "JavaScript",
        "CSS3",
        "Engineering",
        "Jr. HTML5 Ad Developer",
        "Full-Time",
        "Remote",
    ]
    assert first.description.startswith("Along with our partner")
    # Descriptions are HTML in some rows: they are stored as plain text.
    assert jobs[4].description == "Our ledger service is written in Rust"


def test_tecla_config_skips_us_residency_rows():
    """`usaOnly` is the board's only eligibility flag: a US-only role is not ours."""
    jobs = JsonListProvider(TECLA_CONFIG).parse(_json_page(TECLA_PAYLOAD))
    ids = [job.external_id for job in jobs]

    assert "3412" not in ids  # Data Scientist (US only)
    assert "3501" not in ids  # Rust Engineer (US only) — matching work still skipped
    # A row that omits the flag entirely is not skipped, only a truthy one is.
    assert "3502" in ids
    assert next(job for job in jobs if job.external_id == "3502").location == "Remote"


def test_tecla_config_applies_the_language_gate_to_the_board():
    scraper = DiscoveryScraper("json_list", TECLA_CONFIG)
    jobs = scraper.parse(_json_page(TECLA_PAYLOAD))

    # Rust reaches the gate through the skill chips (3500), the subtitle (3404)
    # and the description (3502); the Python/SQL rows and the year-old SAP
    # posting (dropped by `max_age_days`) do not match.
    assert [job.title for job in jobs] == [
        "Staff Engineer (AI Infrastructure)",
        "Senior Rust Engineer",
        "Backend Developer (Payments)",
    ]
    assert all(job.location == "Remote" for job in jobs)
    assert scraper._location_dropped == 0
    assert scraper._location_unknown == 0
    # A quiet board is a success, not a format-change failure.
    assert scraper.allow_empty is True

    # Every row is labelled `Remote`, so a narrower location list must be able
    # to drop them: that is what enforces the LatAm premise on this board.
    strict = DiscoveryScraper("json_list", {**TECLA_CONFIG, "locations": ["latam"]})
    assert strict.parse(_json_page(TECLA_PAYLOAD)) == []
    assert strict._location_dropped == 3


def test_tecla_config_walks_the_api_pagination_to_the_last_page():
    provider = JsonListProvider(TECLA_CONFIG)

    assert provider.results_url() == "https://api.tecla.io/api/jobs/getPublicJobs/?page=1"
    # `countPages`/`current` end the walk at 4 of 4 instead of `max_pages` (8).
    assert provider.next_page_url(_json_page(TECLA_PAYLOAD)) == (
        "https://api.tecla.io/api/jobs/getPublicJobs/?page=2"
    )
    last = _json_page(
        {"data": {"jobs": [], "pagination": {"current": 4, "countPages": 4}}}
    )
    assert provider.next_page_url(last) is None
    # A payload that loses the bound ends the walk instead of fetching 8 empty
    # pages; `max_pages` is only the cap for a board that grows.
    assert provider.next_page_url(_json_page({"data": {"jobs": []}})) is None
    capped = JsonListProvider({**TECLA_CONFIG, "max_pages": 2})
    assert capped.next_page_url(_json_page(TECLA_PAYLOAD)) is not None
    assert capped.next_page_url(_json_page(TECLA_PAYLOAD)) is None


def test_tecla_config_is_registered_and_dispatched():
    provider = get_discovery_provider("json_list", TECLA_CONFIG)
    assert provider.requires_key is False
    JsonListProvider.validate_config(TECLA_CONFIG)
    metadata = JsonListProvider.config_metadata()["optional"]
    for key in (
        "last_page_path",
        "current_page_path",
        "skip_if_true",
        "tags_paths",
        "location_tpl",
        "match_paths",
    ):
        assert key in metadata

    scraper = get_scraper(SimpleNamespace(type=SourceType.discovery, config=TECLA_CONFIG))
    # `{page}` renders to the first page: a json_list board is walked by `{page}`.
    assert (
        scraper.first_fetch_url("https://app.tecla.io/jobs")
        == "https://api.tecla.io/api/jobs/getPublicJobs/?page=1"
    )
    # The API host publishes no robots.txt (404 → allowed); the human board URL
    # stays the source's `url` for the UI and is never fetched.
    assert scraper.robots_url(TECLA_CONFIG["url"]) == TECLA_CONFIG["url"]
    assert scraper.allow_empty is True


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
    # `max_results` caps what is kept; the board itself is read page by page
    # (SmartRecruiters caps `limit` at 100 per request and pages with `offset`).
    assert provider.results_url() == (
        "https://api.smartrecruiters.com/v1/companies/acme/postings?limit=100"
    )
    assert provider._page_url(provider.results_url(), 100) == (
        "https://api.smartrecruiters.com/v1/companies/acme/postings"
        "?limit=100&offset=100"
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


def test_brave_pagination_advances_one_page_at_a_time():
    """Brave's offset is a page number and next_offset would skip a page."""
    provider = BraveProvider({"query": "rust"})
    page = _json_page(
        {"web": {"results": []}, "query": {"more_results_available": True}}
    )
    for expected_page in range(1, 10):
        next_url = provider.next_page_url(page)
        assert next_url and f"offset={expected_page}" in next_url
    # Brave caps paging at offset 9; the tenth page is already the last one.
    assert provider.next_page_url(page) is None

    finished = _json_page(
        {"web": {"results": []}, "query": {"more_results_available": False}}
    )
    assert BraveProvider({"query": "rust"}).next_page_url(finished) is None


def test_search_providers_use_every_configured_query():
    brave = BraveProvider({"queries": ["rust", "python"], "count": 5})
    assert "q=rust" in brave.results_url()
    brave_page = _json_page(
        {"web": {"results": []}, "query": {"more_results_available": False}}
    )
    next_url = brave.next_page_url(brave_page)
    assert next_url and "q=python" in next_url and "offset" not in next_url
    assert brave.next_page_url(brave_page) is None

    google = GoogleCseProvider({"queries": ["rust", "python"], "cx": "c"}, "K")
    assert "q=rust" in google.results_url()
    empty_page = _json_page({"items": []})
    next_url = google.next_page_url(empty_page)
    assert next_url and "q=python" in next_url and "start" not in next_url
    assert google.next_page_url(empty_page) is None


def test_search_provider_rotation_reads_every_query_before_paginating():
    """A sweep must reach query #2 even when query #1 has more results.

    Search APIs report `more_results_available` on almost every page, so the
    old offset-first loop spent the whole page budget inside query #1 and the
    Lever/Greenhouse/SmartRecruiters queries never ran.
    """
    config = {"queries": ["rust ashby", "golang lever"], "max_pages": 2}
    provider = BraveProvider(config)
    provider.rotate_queries = True
    page = _json_page(
        {"web": {"results": []}, "query": {"more_results_available": True}}
    )

    first = provider.next_page_url(page)
    assert first and "q=rust+ashby" in first and "offset=1" in first
    # `max_pages: 2` is the per-query budget: now move to the next query.
    second = provider.next_page_url(page)
    assert second and "q=golang+lever" in second and "offset" not in second
    # Page two of the last query is still inside the budget...
    third = provider.next_page_url(page)
    assert third and "q=golang+lever" in third and "offset=1" in third
    # ...and then the query list is exhausted.
    assert provider.next_page_url(page) is None

    # A non-sweep source keeps paging the current query as before.
    plain = BraveProvider({"queries": ["rust ashby", "golang lever"], "max_pages": 1})
    next_url = plain.next_page_url(page)
    assert next_url and "q=rust+ashby" in next_url and "offset=1" in next_url


def test_search_providers_reject_a_malformed_queries_list():
    with pytest.raises(ValueError, match="queries"):
        BraveProvider.validate_config({"queries": "rust"}, has_api_key=True)
    with pytest.raises(ValueError, match="queries"):
        BraveProvider.validate_config({"queries": ["rust", ""]}, has_api_key=True)


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
        "https://serpapi.com/search?engine=linkedin_jobs&start=11&api_key=KEY-1"
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


def test_serpapi_reads_the_posting_age_from_the_extensions_chip():
    """Google Jobs reports the age as a chip, not ``detected_extensions``."""
    provider = SerpApiProvider(
        {"engine": "google_jobs", "query": "rust", "parse_mode": "results"}, "K"
    )
    payload = {
        "jobs_results": [
            {
                "title": "Rust Engineer",
                "extensions": ["5 days ago", "Full-time"],
                "apply_options": [{"link": "https://a.example/1"}],
            },
            {
                "title": "Go Engineer",
                "extensions": ["30+ days ago", "$120K-$160K a year"],
                "apply_options": [{"link": "https://a.example/2"}],
            },
            {
                "title": "C++ Engineer",
                "extensions": ["1 year contract", "Full-time"],
                "apply_options": [{"link": "https://a.example/3"}],
            },
            {
                "title": "Undated Engineer",
                "extensions": ["Full-time", "Health insurance"],
                "apply_options": [{"link": "https://a.example/4"}],
            },
        ]
    }

    jobs = provider.parse(_json_page(payload))

    today = date.today()
    assert jobs[0].posted_date == today - timedelta(days=5)
    assert jobs[1].posted_date == today - timedelta(days=30)
    # A contract length and a salary are not posting ages.
    assert jobs[2].posted_date is None
    assert jobs[3].posted_date is None


def test_serpapi_forwards_locale_params():
    """`gl`/`hl` pin the Google Jobs locale instead of defaulting to the US."""
    provider = SerpApiProvider(
        {"engine": "google_jobs", "query": "golang remote", "gl": "br", "hl": "pt-BR"},
        "K",
    )
    url = provider.results_url()
    assert "gl=br" in url
    assert "hl=pt-BR" in url

    # Both are optional, so existing sources keep their previous request.
    plain = SerpApiProvider({"engine": "google_jobs", "query": "golang remote"}, "K")
    assert "gl=" not in plain.results_url()
    assert "hl=" not in plain.results_url()

    # The source form reads these from the published provider contract.
    metadata = SerpApiProvider.config_metadata()
    assert {"gl", "hl", "remote_only", "via_filter"} <= set(metadata["optional"])
    # The example is what the form pre-fills: do not steer users into the
    # Brazil-localised index that returns `Fully empty` for global remote jobs.
    assert metadata["example"]["gl"] == "us"
    assert "location" not in metadata["example"]


def test_serpapi_robots_url_exempts_the_vendor_api_only():
    """`serpapi.com/robots.txt` disallows `/search?`, but that is our API call."""
    provider = SerpApiProvider({"engine": "google_jobs", "query": "c++ remote"}, "K")
    assert provider.robots_url(provider.results_url()) is None
    assert provider.robots_url("https://serpapi.com/search?engine=google_jobs&start=10") is None

    # Board/detail links are real pages and keep their normal robots check.
    board = "https://www.glassdoor.com/job-listing/cpp-engineer-acme-JV_1.htm"
    assert provider.robots_url(board) == board
    assert provider.robots_url("https://notserpapi.com/search?q=cpp") == (
        "https://notserpapi.com/search?q=cpp"
    )

    scraper = DiscoveryScraper("serpapi", {"engine": "google_jobs", "query": "rust"}, "K")
    assert scraper.robots_url(provider.results_url()) is None


def test_serpapi_hashes_long_google_job_ids_for_the_external_id_column():
    """Google's base64 job_id is longer than jobs.external_id (255)."""
    long_id = "A" * 350
    provider = SerpApiProvider(
        {"engine": "google_jobs", "query": "c++ remote", "parse_mode": "results"}, "K"
    )
    payload = {
        "jobs_results": [
            {
                "title": "C++ Engineer",
                "company_name": "Acme",
                "job_id": long_id,
                "apply_options": [{"link": "https://acme.example/jobs/1"}],
            }
        ]
    }

    job = provider.parse(_json_page(payload))[0]

    assert job.external_id.startswith("serpapi:")
    assert len(job.external_id) <= 255
    # Stable naming across runs, so deduplication keeps working.
    assert job.external_id == provider.parse(_json_page(payload))[0].external_id


def test_serpapi_next_page_url_keeps_the_api_key():
    """SerpApi's `next` link omits `api_key`; following it verbatim 401s."""
    provider = SerpApiProvider({"engine": "google_jobs", "query": "rust"}, "KEY-1")
    page = _json_page(
        {
            "serpapi_pagination": {
                "next": "https://serpapi.com/search?engine=google_jobs&q=rust&start=10"
            }
        }
    )
    next_url = provider.next_page_url(page)
    assert "start=10" in next_url
    assert "api_key=KEY-1" in next_url

    # A key already present is not duplicated.
    already_keyed = _json_page(
        {
            "serpapi_pagination": {
                "next": "https://serpapi.com/search?engine=google_jobs&start=20&api_key=OLD"
            }
        }
    )
    keyed_url = provider.next_page_url(already_keyed)
    assert keyed_url.count("api_key=") == 1
    assert "api_key=OLD" in keyed_url

    assert provider.next_page_url(_json_page({})) is None


def test_serpapi_remote_only_filters_results():
    provider = SerpApiProvider(
        {"query": "golang", "parse_mode": "results", "remote_only": True}, "K"
    )
    payload = {
        "jobs_results": [
            {
                "title": "Go Engineer",
                "apply_options": [{"link": "https://a.example/1"}],
                "detected_extensions": {"work_from_home": True},
            },
            {
                "title": "C++ Engineer",
                "location": "Remote, Brazil",
                "apply_options": [{"link": "https://a.example/2"}],
            },
            {
                "title": "Rust Engineer",
                "location": "Sao Paulo, Brazil",
                "extensions": ["Remote"],
                "apply_options": [{"link": "https://a.example/3"}],
            },
            {
                "title": "Onsite Engineer",
                "location": "Sao Paulo, Brazil",
                "apply_options": [{"link": "https://a.example/4"}],
            },
        ]
    }
    page = _json_page(payload)
    assert [job.title for job in provider.parse(page)] == [
        "Go Engineer",
        "C++ Engineer",
        "Rust Engineer",
    ]
    # The same filter applies when results are followed as links instead.
    links = provider.result_links(page)
    assert links == [
        "https://a.example/1",
        "https://a.example/2",
        "https://a.example/3",
    ]


def test_serpapi_via_filter_matches_board_attribution():
    provider = SerpApiProvider(
        {"query": "glassdoor", "parse_mode": "results", "via_filter": "glassdoor"}, "K"
    )
    payload = {
        "jobs_results": [
            {
                "title": "Go Engineer",
                "via": "Glassdoor",
                "apply_options": [{"link": "https://glassdoor.com/jobs/1"}],
            },
            {
                "title": "Rust Engineer",
                "via": "LinkedIn",
                "apply_options": [
                    {"title": "LinkedIn", "link": "https://linkedin.com/jobs/2"}
                ],
            },
            {
                "title": "C++ Engineer",
                "apply_options": [
                    {"title": "Glassdoor", "link": "https://boards.example/jobs/3"}
                ],
            },
        ]
    }
    jobs = provider.parse(_json_page(payload))
    assert [job.title for job in jobs] == ["Go Engineer", "C++ Engineer"]


def test_relative_age_parses_serp_labels():
    assert relative_age("Just posted") == date.today().isoformat()
    assert relative_age("30+ days ago") == (date.today() - timedelta(days=30)).isoformat()
    assert relative_age("2 weeks ago") == (date.today() - timedelta(days=14)).isoformat()
    assert relative_age("5 hours ago") == date.today().isoformat()
    assert relative_age("last month") is None
    assert relative_age(None) is None


def test_relative_age_parses_compact_card_labels():
    assert relative_age("1D") == (date.today() - timedelta(days=1)).isoformat()
    assert relative_age("4d") == (date.today() - timedelta(days=4)).isoformat()
    assert relative_age("3H") == date.today().isoformat()
    # A title-like value is not a compact age label.
    assert relative_age("Level 3D") is None


def test_relative_age_parses_portuguese_labels():
    assert relative_age("há 2 horas") == date.today().isoformat()
    assert relative_age("Há 3 dias") == (date.today() - timedelta(days=3)).isoformat()
    assert relative_age("2 semanas atrás") == (date.today() - timedelta(days=14)).isoformat()
    assert relative_age("publicado há 1 mês") == (date.today() - timedelta(days=30)).isoformat()
    assert relative_age("ontem") == (date.today() - timedelta(days=1)).isoformat()
    assert relative_age("hoje") == date.today().isoformat()


def test_parse_html_list_removes_status_badge_from_title():
    page = ScrapedPage(
        html_content=(
            '<article class="job"><h3>Rust Engineer '
            '<span class="badge">Nova</span></h3><a href="/jobs/1">Open</a></article>'
        ),
        status_code=200,
        final_url="https://board.example/jobs",
    )
    jobs = parse_html_list(
        page,
        {
            "item_selector": "article.job",
            "title_selector": "h3",
            "title_exclude_selector": ".badge",
            "url_selector": "a",
        },
    )
    assert jobs[0].title == "Rust Engineer"


def test_parse_html_list_uses_configured_company_when_card_has_none():
    page = ScrapedPage(
        html_content='<article class="job"><a href="/jobs/1">Solo Role</a></article>',
        status_code=200,
        final_url="https://board.example/jobs",
    )
    jobs = parse_html_list(
        page,
        {
            "item_selector": "article.job",
            "title_selector": "a",
            "url_selector": "a",
            "company": "Acme",
        },
    )
    assert jobs[0].company == "Acme"


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


def _search_results_page(links: list[str]) -> ScrapedPage:
    return _json_page({"web": {"results": [{"url": link} for link in links]}})


async def test_ats_sweep_turns_search_results_into_board_apis():
    """One search result becomes one live board sweep, deduplicated per org."""
    scraper = DiscoveryScraper(
        "brave",
        {"query": "site:jobs.ashbyhq.com rust", "sweep_ats": True},
    )
    page = _search_results_page(
        [
            "https://jobs.ashbyhq.com/acme/123",
            "https://jobs.ashbyhq.com/acme/456",  # same org -> one board
            "https://jobs.lever.co/acme/abc",
            "https://boards.greenhouse.io/acme/jobs/1",
            "https://jobs.smartrecruiters.com/Acme/123",
            "https://example.com/acme/jobs/1",  # not an ATS board
        ]
    )

    assert await scraper.discover_urls(page) == [
        "https://api.ashbyhq.com/posting-api/job-board/acme",
        "https://api.lever.co/v0/postings/acme?mode=json&limit=100",
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
        "https://api.smartrecruiters.com/v1/companies/Acme/postings?limit=100",
    ]
    assert scraper.sweep_enabled is True
    assert scraper.allow_empty is True
    assert scraper.default_max_results == 40
    # Re-reading the same results page (e.g. a paginated query) changes nothing.
    assert await scraper.discover_urls(page) == []


def test_ats_sweep_budget_knobs_are_published_in_the_provider_metadata():
    """A sweep knob that is missing here cannot be set through the API form."""
    expected = {
        "sweep_ats",
        "keywords",
        "exclude_keywords",
        "locations",
        "max_boards",
        "max_jobs",
        "match_in",
        "board_rate_limit_seconds",
        "min_boards_per_query",
        "sweep_max_seconds",
        "max_age_days",
        # The levers over *which* boards the index offers, the per-board read
        # cap and the rotation that spreads the budget across runs: a sweep
        # without them cannot grow beyond what the index ranks.
        "seed_urls",
        "query_hints",
        "board_max_jobs",
        "board_reread_days",
        "max_jobs_per_board",
    }
    for cls in (GoogleCseProvider, BingProvider, BraveProvider):
        assert expected <= set(cls.config_metadata()["optional"]), cls.provider_name


def test_query_hints_expand_every_configured_query():
    """The query wording is the only automatic lever on which boards appear.

    Measured: Brave never ranks Alpaca's Greenhouse board for
    ``golang site:greenhouse.io`` (pages 1-4), but does for
    ``golang remote brazil site:greenhouse.io``.  A hint is source-owned wording
    appended to each query; it never filters a posting.
    """
    provider = BraveProvider(
        {"queries": ["golang", "rust"], "query_hints": ["remote brazil"]}
    )

    assert provider._queries() == [
        "golang",
        "rust",
        "golang remote brazil",
        "rust remote brazil",
    ]
    assert provider.query_count == 4
    # Without hints the configured queries are used verbatim.
    assert BraveProvider({"query": "golang"})._queries() == ["golang"]

    with pytest.raises(ValueError):
        BraveProvider.validate_config({"query_hints": "remote brazil"})
    with pytest.raises(ValueError):
        BraveProvider.validate_config({"seed_urls": "https://jobs.lever.co/acme"})


async def test_ats_sweep_does_not_reparse_board_payloads_as_search_results():
    """The worker asks every fetched page for URLs; a Lever board is a list."""
    scraper = DiscoveryScraper("brave", {"query": "rust", "sweep_ats": True})
    search_page = _search_results_page(["https://jobs.lever.co/acme/1"])
    board_url = (await scraper.discover_urls(search_page))[0]
    board_page = ScrapedPage(
        html_content=json.dumps(
            [{"id": "1", "text": "Rust Engineer", "hostedUrl": "https://jobs.lever.co/acme/1"}]
        ),
        status_code=200,
        final_url=board_url,
    )

    assert await scraper.discover_urls(board_page) == []
    assert [job.title for job in scraper.parse(board_page)] == ["Rust Engineer"]


async def test_ats_sweep_respects_max_boards():
    scraper = DiscoveryScraper(
        "brave",
        {"query": "rust", "sweep_ats": True, "max_boards": 2},
    )
    page = _search_results_page(
        [
            "https://jobs.ashbyhq.com/acme/1",
            "https://jobs.lever.co/acme/1",
            "https://boards.greenhouse.io/acme/jobs/1",
        ]
    )

    urls = await scraper.discover_urls(page)

    assert len(urls) == 2
    assert scraper.default_max_results == 2


async def test_ats_sweep_reports_the_boards_it_could_not_afford(caplog):
    """`offered` must count the boards `max_boards` left unread.

    Without it a budget-bound sweep and a search index that only returns a
    couple of boards per query look identical in the run log.
    """
    scraper = DiscoveryScraper(
        "brave",
        {
            "query": "rust",
            "sweep_ats": True,
            "max_boards": 2,
            "keywords": ["rust"],
        },
    )
    page = _search_results_page(
        [
            "https://jobs.ashbyhq.com/acme/1",
            "https://jobs.lever.co/beta/1",
            "https://boards.greenhouse.io/gamma/jobs/1",  # offered, not read
        ]
    )

    with caplog.at_level(logging.INFO, logger="scrapers.discovery"):
        urls = await scraper.discover_urls(page)
        board_page = ScrapedPage(
            html_content=json.dumps(
                [{"id": "1", "text": "Rust Engineer", "hostedUrl": urls[1]}]
            ),
            status_code=200,
            final_url=urls[1],
        )
        assert [job.title for job in scraper.parse(board_page)] == ["Rust Engineer"]
        scraper.normalize([])

    assert len(urls) == 2
    # The manifest names each board that was read, with the query that found it.
    assert "ats_sweep_board query=rust ats=ashby url=" in caplog.text
    assert "ats_sweep_board query=rust ats=lever url=" in caplog.text
    assert "boards.greenhouse.io" not in caplog.text
    # Openings vs kept: the board was read, one opening survived the filter.
    assert "ats_sweep_board_jobs url=" in caplog.text
    assert "openings=1 kept=1" in caplog.text
    # Three boards offered, two affordable.
    assert "boards=2 offered=3 jobs=0 stale=0 undated=0 queries=1" in caplog.text


async def test_ats_sweep_stops_paging_when_board_budget_is_spent():
    """No later search page can add a board once ``max_boards`` is reached."""
    scraper = DiscoveryScraper(
        "brave",
        {"query": "rust", "sweep_ats": True, "max_boards": 1},
    )
    page = _json_page(
        {
            "web": {"results": [{"url": "https://jobs.ashbyhq.com/acme/1"}]},
            "query": {"more_results_available": True},
        }
    )

    assert await scraper.discover_urls(page)
    assert scraper.next_page_url(page) is None


def test_ats_sweep_filters_board_jobs_and_caps_max_jobs():
    scraper = DiscoveryScraper(
        "brave",
        {
            "query": "rust",
            "sweep_ats": True,
            "keywords": ["rust"],
            "exclude_keywords": ["intern"],
            "locations": ["brazil"],
            "max_jobs": 1,
        },
    )
    board_url = "https://api.ashbyhq.com/posting-api/job-board/acme"
    board = resolve_ats_board("https://jobs.ashbyhq.com/acme/1")
    assert board is not None
    assert scraper._register_board(board) == board_url
    payload = {
        "jobs": [
            {
                "id": "1",
                "title": "Senior Rust Engineer",
                "location": "Remote - Brazil",
                "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                "descriptionHtml": "<p>Rust services</p>",
                "department": "Engineering",
                "employmentType": "FullTime",
            },
            {
                "id": "2",
                "title": "Rust Intern",
                "location": "Brazil",
                "jobUrl": "https://jobs.ashbyhq.com/acme/2",
                "descriptionHtml": "<p>Rust</p>",
            },
            {
                "id": "3",
                "title": "Python Engineer",
                "location": "Brazil",
                "jobUrl": "https://jobs.ashbyhq.com/acme/3",
                "descriptionHtml": "<p>Python</p>",
            },
            {
                "id": "4",
                "title": "Rust Engineer",
                "location": "Portugal",
                "jobUrl": "https://jobs.ashbyhq.com/acme/4",
                "descriptionHtml": "<p>Rust</p>",
            },
            {
                "id": "5",
                "title": "Rust Engineer",
                "location": "Brazil",
                "jobUrl": "https://jobs.ashbyhq.com/acme/5",
                "descriptionHtml": "<p>Rust</p>",
            },
        ]
    }
    page = ScrapedPage(
        html_content=json.dumps(payload),
        status_code=200,
        final_url=board_url,
    )

    jobs = scraper.parse(page)

    assert [job.external_id for job in jobs] == ["1"]
    assert jobs[0].title == "Senior Rust Engineer"
    assert "Remote - Brazil" in jobs[0].tags
    assert "Engineering" in jobs[0].tags
    assert jobs[0].location == "Remote - Brazil"
    # max_jobs is per source run, not per board page.
    assert scraper.parse(page) == []


def test_ats_sweep_location_gate_uses_detected_location_and_keeps_unknown():
    """A term in the body must not keep a job; a missing location must.

    Regression: the sweep matched ``locations`` against title/tags/description,
    so a "Portugal" opening that mentioned Brazil was stored while a board that
    reports no location had every job silently dropped.
    """
    scraper = DiscoveryScraper(
        "brave",
        {"query": "rust", "sweep_ats": True, "locations": ["brazil"]},
    )
    board_url = "https://api.ashbyhq.com/posting-api/job-board/acme"
    board = resolve_ats_board("https://jobs.ashbyhq.com/acme/1")
    assert board is not None
    assert scraper._register_board(board) == board_url
    payload = {
        "jobs": [
            {
                "id": "1",
                "title": "Rust Engineer",
                "location": "Lisbon, Portugal",
                "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                "descriptionHtml": "<p>Our team meets in Brazil once a year.</p>",
            },
            {
                "id": "2",
                "title": "Rust Engineer",
                "jobUrl": "https://jobs.ashbyhq.com/acme/2",
                "descriptionHtml": "<p>The board reports no location.</p>",
            },
            {
                "id": "3",
                "title": "Rust Engineer",
                "location": "Remote - Brazil",
                "jobUrl": "https://jobs.ashbyhq.com/acme/3",
                "descriptionHtml": "<p>Rust services.</p>",
            },
        ]
    }
    page = ScrapedPage(
        html_content=json.dumps(payload), status_code=200, final_url=board_url
    )

    jobs = scraper.parse(page)

    assert [job.external_id for job in jobs] == ["2", "3"]
    assert scraper._location_dropped == 1
    assert scraper._location_unknown == 1


# --- whole-board reads -------------------------------------------------------
# A board is a JSON dump of every opening the company has. Reading it as one
# `limit=100` request is how a 715-posting Lever board lost 615 postings without
# a single log line saying so.


def _lever_board_page(start: int, count: int) -> list[dict]:
    return [
        {
            "id": str(start + index),
            "text": f"Go Engineer {start + index}",
            "hostedUrl": f"https://jobs.lever.co/acme/{start + index}",
            "createdAt": 1_700_000_000_000,
            "categories": {"location": "Remote - Brazil"},
            "descriptionPlain": "Go services",
        }
        for index in range(count)
    ]


def _lever_skip(url: str) -> int:
    return int(url.split("skip=")[1].split("&")[0]) if "skip=" in url else 0


async def test_lever_board_is_read_page_by_page(monkeypatch, caplog):
    """Every posting of a Lever board is read, not the first page only."""
    import scrapers.discovery as discovery

    requested: list[str] = []

    async def fake_fetch_html(url, *, auth=None, max_bytes=None):
        requested.append(url)
        skip = _lever_skip(url)
        # 250 postings in pages of 100: 100 + 100 + 50.
        count = max(0, min(100, 250 - skip))
        return ScrapedPage(
            html_content=json.dumps(_lever_board_page(skip, count)),
            status_code=200,
            final_url=url,
        )

    monkeypatch.setattr(discovery, "fetch_html", fake_fetch_html)
    provider = LeverProvider({"company": "acme", "limit": 100})
    url = provider.results_url()

    with caplog.at_level(logging.INFO, logger="scrapers.discovery"):
        page = await provider.fetch(url)

    assert len(requested) == 3
    assert _lever_skip(requested[1]) == 100
    assert _lever_skip(requested[2]) == 200
    jobs = provider.parse(page)
    assert len(jobs) == 250
    assert jobs[-1].external_id == "249"
    # The sweep looks the board parser up by the URL it registered.
    assert page.final_url == url
    assert "ats_board_read url=" in caplog.text
    assert "pages=3 postings=250" in caplog.text
    # Nothing was cut, so nothing may look truncated.
    assert "ats_board_truncated" not in caplog.text


async def test_board_read_stops_at_board_max_jobs_and_logs_truncation(monkeypatch, caplog):
    """A cap that silently shortens a board is what hid 615 Lever postings."""
    import scrapers.discovery as discovery

    requested: list[str] = []

    async def fake_fetch_html(url, *, auth=None, max_bytes=None):
        requested.append(url)
        skip = _lever_skip(url)
        count = max(0, min(100, 250 - skip))
        return ScrapedPage(
            html_content=json.dumps(_lever_board_page(skip, count)),
            status_code=200,
            final_url=url,
        )

    monkeypatch.setattr(discovery, "fetch_html", fake_fetch_html)
    provider = LeverProvider({"company": "acme", "limit": 100, "board_max_jobs": 120})
    url = provider.results_url()

    with caplog.at_level(logging.INFO, logger="scrapers.discovery"):
        page = await provider.fetch(url)

    # Two pages (100 + 100) reach the 120 cap; the third is never requested.
    assert len(requested) == 2
    assert len(provider.parse(page)) == 120
    assert "ats_board_truncated url=" in caplog.text
    assert "postings=120 cap=120" in caplog.text


async def test_board_read_keeps_pages_already_read_when_a_later_page_fails(
    monkeypatch, caplog
):
    """A 429 on page 3 must cost the board the rest, not everything read so far."""
    import scrapers.discovery as discovery

    async def fake_fetch_html(url, *, auth=None, max_bytes=None):
        skip = _lever_skip(url)
        if skip >= 200:
            raise httpx.ConnectError("board throttled")
        return ScrapedPage(
            html_content=json.dumps(_lever_board_page(skip, 100)),
            status_code=200,
            final_url=url,
        )

    monkeypatch.setattr(discovery, "fetch_html", fake_fetch_html)
    provider = LeverProvider({"company": "acme", "limit": 100})

    with caplog.at_level(logging.WARNING, logger="scrapers.discovery"):
        page = await provider.fetch(provider.results_url())

    assert len(provider.parse(page)) == 200
    assert "ats_board_page_failed url=" in caplog.text
    assert "page=3" in caplog.text


def test_board_read_cap_prefers_board_max_jobs_then_max_results():
    assert LeverProvider({"company": "acme"}).board_max_jobs() == 1000
    assert LeverProvider({"company": "acme", "max_results": 5}).board_max_jobs() == 5
    assert (
        LeverProvider({"company": "acme", "max_results": 5, "board_max_jobs": 700})
        .board_max_jobs()
        == 700
    )


def _smartrecruiters_page(offset: int, count: int) -> dict:
    return {
        "totalFound": 150,
        "content": [
            {
                "id": f"{900000 + offset + index}",
                "name": f"Go Engineer {offset + index}",
                "company": {"identifier": "acme", "name": "Acme"},
                "location": {"fullLocation": "Remote - Brazil"},
                "releasedDate": "2026-10-01",
            }
            for index in range(count)
        ],
    }


async def test_smartrecruiters_board_is_read_page_by_page(monkeypatch):
    """SmartRecruiters pages with ``offset``; the folded payload keeps its shape."""
    import scrapers.discovery as discovery

    requested: list[str] = []

    async def fake_fetch_html(url, *, auth=None, max_bytes=None):
        requested.append(url)
        offset = int(url.split("offset=")[1].split("&")[0]) if "offset=" in url else 0
        count = max(0, min(100, 150 - offset))
        return ScrapedPage(
            html_content=json.dumps(_smartrecruiters_page(offset, count)),
            status_code=200,
            final_url=url,
        )

    monkeypatch.setattr(discovery, "fetch_html", fake_fetch_html)
    provider = SmartRecruitersProvider({"company": "acme"})
    url = provider.results_url()

    page = await provider.fetch(url)

    assert len(requested) == 2
    assert "offset=100" in requested[1]
    assert page.final_url == url
    jobs = provider.parse(page)
    assert len(jobs) == 150
    assert jobs[-1].external_id == "900149"


# --- board budget ------------------------------------------------------------


def _query_page(prefix: str, count: int = 4) -> ScrapedPage:
    """A search page offering ``count`` Ashby boards, with a next page."""
    return _json_page(
        {
            "web": {
                "results": [
                    {"url": f"https://jobs.ashbyhq.com/{prefix}{index}/1"}
                    for index in range(count)
                ]
            },
            "query": {"more_results_available": True},
        }
    )


async def test_ats_sweep_shares_the_board_budget_between_queries(caplog):
    """Each query gets an equal share; the first one cannot eat the budget.

    Measured before the fix: on a 12-query sweep the first two queries spent 30
    of the 50 slots, and the two ``site:greenhouse.io`` queries registered two
    boards each - both already read by an earlier query.
    """
    scraper = DiscoveryScraper(
        "brave",
        {
            "queries": ["q1", "q2", "q3"],
            "sweep_ats": True,
            "max_boards": 6,
            "min_boards_per_query": 0,
        },
    )
    first = _query_page("a")

    with caplog.at_level(logging.INFO, logger="scrapers.discovery"):
        urls = await scraper.discover_urls(first)
        assert scraper.next_page_url(first) is not None
        second = _query_page("b")
        urls += await scraper.discover_urls(second)
        assert scraper.next_page_url(second) is not None
        urls += await scraper.discover_urls(_query_page("c"))
        scraper.normalize([])

    # Six slots, three queries, four boards offered each: 2 + 2 + 2.
    assert len(urls) == 6
    assert "ats_sweep_query query=q1 offered=4 read=2 blocked=2 dead=0" in caplog.text
    assert "ats_sweep_query query=q2 offered=4 read=2 blocked=2 dead=0" in caplog.text
    assert "ats_sweep_query query=q3 offered=4 read=2 blocked=2 dead=0" in caplog.text


async def test_ats_sweep_reads_seed_boards_before_the_index(caplog):
    """A board the index never offers is still swept when the source names it.

    Measured: ``golang site:greenhouse.io`` does not return Alpaca's Greenhouse
    board on pages 1-4, so no board budget recovers the postings that the same
    source finds by hand with ``golang remote brazil site:greenhouse.io``.
    """
    scraper = DiscoveryScraper(
        "brave",
        {
            "query": "golang site:greenhouse.io",
            "sweep_ats": True,
            "max_boards": 2,
            "seed_urls": [
                "https://job-boards.greenhouse.io/alpaca/jobs/6195696004",
                "https://job-boards.greenhouse.io/alpaca/jobs/6233042004",  # same board
                "https://example.com/not-a-board",
            ],
        },
    )

    with caplog.at_level(logging.INFO, logger="scrapers.discovery"):
        urls = await scraper.discover_urls(
            _search_results_page(["https://jobs.lever.co/acme/1"])
        )
        scraper.normalize([])

    # The seed board is read first and deduplicated to one board; the rest of
    # the budget still goes to the index.
    assert urls == [
        "https://boards-api.greenhouse.io/v1/boards/alpaca/jobs?content=true",
        "https://api.lever.co/v0/postings/acme?mode=json&limit=100",
    ]
    assert (
        "ats_sweep_seed_skipped url=https://example.com/not-a-board "
        "reason=not_an_ats_board" in caplog.text
    )
    assert "seeds=3" in caplog.text
    # Seeds are registered once, not once per search page.
    assert await scraper.discover_urls(_search_results_page([])) == []


async def test_ats_sweep_seed_boards_consume_the_budget(caplog):
    """A seed is not a free extra request: it takes a slot like any board."""
    scraper = DiscoveryScraper(
        "brave",
        {
            "query": "golang",
            "sweep_ats": True,
            "max_boards": 1,
            "seed_urls": [
                "https://job-boards.greenhouse.io/alpaca/jobs/6195696004",
                "https://jobs.lever.co/acme/1",
            ],
        },
    )

    with caplog.at_level(logging.INFO, logger="scrapers.discovery"):
        urls = await scraper.discover_urls(
            _search_results_page(["https://jobs.ashbyhq.com/acme/1"])
        )

    assert urls == [
        "https://boards-api.greenhouse.io/v1/boards/alpaca/jobs?content=true"
    ]
    assert (
        "ats_sweep_seed_skipped url=https://jobs.lever.co/acme/1 reason=board_budget"
        in caplog.text
    )


async def test_ats_sweep_reads_the_best_matching_board_first():
    """With one slot left, the result's own snippet decides which board is read."""
    scraper = DiscoveryScraper(
        "brave",
        {
            "query": "golang remote",
            "sweep_ats": True,
            "max_boards": 1,
            "keywords": ["golang"],
            "locations": ["brazil"],
        },
    )
    page = _json_page(
        {
            "web": {
                "results": [
                    {
                        "url": "https://boards.greenhouse.io/acme/jobs/1",
                        "title": "Product Designer",
                        "description": "Design systems.",
                    },
                    {
                        "url": "https://boards.greenhouse.io/alpaca/jobs/6195696004",
                        "title": "Software Engineer - Crypto",
                        "description": "Golang services, remote from Brazil.",
                    },
                ]
            }
        }
    )

    urls = await scraper.discover_urls(page)

    assert urls == [
        "https://boards-api.greenhouse.io/v1/boards/alpaca/jobs?content=true"
    ]


def test_ats_sweep_derives_a_title_only_location():
    """A region written only in the title becomes a stored, filterable location.

    Only the trailing segment may count: "Remote Sensing Engineer" must never
    turn into a remote posting.
    """
    scraper = DiscoveryScraper(
        "brave",
        {
            "query": "engineer",
            "sweep_ats": True,
            "keywords": ["engineer"],
            "locations": ["brazil"],
        },
    )
    board = resolve_ats_board("https://jobs.ashbyhq.com/acme/1")
    assert board is not None
    board_url = scraper._register_board(board)
    titles = [
        "Go Engineer - Remote, Brazil",
        "Go Engineer (Remote, Brazil)",
        "Go Engineer - Remote Sensing",
        "Remote Sensing Engineer",
    ]
    payload = {
        "jobs": [
            {
                "id": str(index),
                "title": title,
                "jobUrl": f"https://jobs.ashbyhq.com/acme/{index}",
                "descriptionHtml": "<p>Go services.</p>",
            }
            for index, title in enumerate(titles)
        ]
    }

    jobs = scraper.parse(
        ScrapedPage(
            html_content=json.dumps(payload), status_code=200, final_url=board_url
        )
    )

    assert {job.external_id: job.location for job in jobs} == {
        "0": "Remote, Brazil",
        "1": "Remote, Brazil",
        "2": None,
        "3": None,
    }
    assert scraper._location_unknown == 2
    assert scraper._location_dropped == 0


async def test_ats_sweep_never_forwards_the_search_key_and_isolates_failures(
    monkeypatch,
):
    scraper = DiscoveryScraper("brave", {"query": "rust", "sweep_ats": True})
    page = _search_results_page(["https://jobs.lever.co/acme/1"])
    board_url = (await scraper.discover_urls(page))[0]
    board_provider = scraper._board_providers[board_url.rstrip("/")]

    captured: dict = {}

    async def failing_fetch(url: str, **kwargs) -> ScrapedPage:
        captured.update(kwargs)
        raise httpx.ConnectError("board is down")

    monkeypatch.setattr(board_provider, "fetch", failing_fetch)

    result = await scraper.fetch(
        board_url, auth=FetchAuth(api_key="search-provider-secret")
    )

    # No credential is sent to a third-party board, and a dead board is an
    # empty page instead of an exception that aborts the whole sweep.
    assert captured == {}
    assert result.html_content == ""
    assert result.status_code == 0
    assert scraper.parse(result) == []
    assert scraper.robots_url(board_url) is None


def test_ats_sweep_page_budget_covers_every_query():
    """`max_pages` is a per-query budget, so the run's page cap multiplies."""
    scraper = DiscoveryScraper(
        "brave",
        {"queries": [f"q{i}" for i in range(12)], "max_pages": 1, "sweep_ats": True},
    )
    assert scraper.page_limit(1) == 12
    assert scraper.page_limit(2) == 24

    # A single-query sweep keeps the configured page count.
    single = DiscoveryScraper("brave", {"query": "rust", "sweep_ats": True})
    assert single.page_limit(1) == 1
    # Non-sweep sources page through results as before.
    two_stage = DiscoveryScraper("brave", {"queries": ["a", "b"], "max_pages": 1})
    assert two_stage.page_limit(1) == 1


async def test_ats_sweep_reserves_boards_for_the_queries_not_visited_yet():
    """The first query must not spend the whole board budget on its own."""
    scraper = DiscoveryScraper(
        "brave",
        {
            "queries": ["rust ashby", "rust lever", "rust greenhouse"],
            "sweep_ats": True,
            "max_boards": 4,
            "min_boards_per_query": 1,
        },
    )
    ashby = _search_results_page(
        [f"https://jobs.ashbyhq.com/org{i}/1" for i in range(5)]
    )

    # 4 slots minus one reserved for each of the two later queries.
    assert len(await scraper.discover_urls(ashby)) == 2

    lever = _search_results_page([f"https://jobs.lever.co/org{i}/1" for i in range(3)])
    assert scraper.next_page_url(ashby)  # advance to query #2
    assert len(await scraper.discover_urls(lever)) == 1  # one slot kept for query #3

    greenhouse = _search_results_page(
        [f"https://boards.greenhouse.io/org{i}/jobs/1" for i in range(3)]
    )
    assert scraper.next_page_url(lever)
    assert len(await scraper.discover_urls(greenhouse)) == 1
    # The budget is now spent, whatever the next query would find.
    assert scraper.next_page_url(greenhouse) is None


def test_ats_sweep_match_in_title_ignores_description_only_hits():
    """A board dump mentions Rust in every blurb; only titles/tags count."""
    scraper = DiscoveryScraper(
        "brave",
        {
            "query": "rust",
            "sweep_ats": True,
            "keywords": ["rust"],
            "match_in": "title",
        },
    )
    board = resolve_ats_board("https://jobs.ashbyhq.com/acme/1")
    assert board is not None
    board_url = scraper._register_board(board)
    payload = {
        "jobs": [
            {
                "id": "1",
                "title": "Senior Rust Engineer",
                "location": "Remote - Brazil",
                "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                "descriptionHtml": "<p>Rust services</p>",
            },
            {
                "id": "2",
                "title": "Growth Lead",
                "location": "Remote - Brazil",
                "jobUrl": "https://jobs.ashbyhq.com/acme/2",
                "descriptionHtml": "<p>Our platform is written in Rust</p>",
            },
        ]
    }
    page = ScrapedPage(
        html_content=json.dumps(payload), status_code=200, final_url=board_url
    )

    assert [job.external_id for job in scraper.parse(page)] == ["1"]

    # Without `match_in`, the description still counts (legacy behaviour).
    anywhere = DiscoveryScraper(
        "brave", {"query": "rust", "sweep_ats": True, "keywords": ["rust"]}
    )
    anywhere._register_board(board)
    assert len(anywhere.parse(page)) == 2


def test_ats_sweep_drops_postings_older_than_max_age_days(caplog):
    """A board repeats the company's whole backlog; only the window is fresh."""
    scraper = DiscoveryScraper(
        "brave",
        {
            "query": "rust",
            "sweep_ats": True,
            "keywords": ["engineer"],
            "max_age_days": 60,
        },
    )
    board = resolve_ats_board("https://jobs.ashbyhq.com/acme/1")
    assert board is not None
    board_url = scraper._register_board(board)
    today = date.today()
    payload = {
        "jobs": [
            {
                "id": "fresh",
                "title": "Rust Engineer",
                "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                "publishedAt": today.isoformat(),
            },
            {
                "id": "stale",
                "title": "Rust Engineer (old)",
                "jobUrl": "https://jobs.ashbyhq.com/acme/2",
                "publishedAt": (today - timedelta(days=61)).isoformat(),
            },
            {
                "id": "undated",
                "title": "Rust Engineer (no date)",
                "jobUrl": "https://jobs.ashbyhq.com/acme/3",
            },
        ]
    }
    page = ScrapedPage(
        html_content=json.dumps(payload), status_code=200, final_url=board_url
    )

    with caplog.at_level(logging.INFO, logger="scrapers.discovery"):
        kept = scraper.parse(page)
        scraper.normalize(kept)

    assert [job.external_id for job in kept] == ["fresh", "undated"]
    # An undated posting is kept, but counted: a source that publishes no dates
    # at all would otherwise look like an empty board.
    assert "stale=1 undated=1 kept=2" in caplog.text
    assert (
        "ats_sweep_summary boards=1 offered=0 jobs=2 stale=1 undated=1"
        in caplog.text
    )


def test_max_age_days_gates_results_mode_search_sources(caplog):
    """Google Jobs is not a sweep, but its rows must respect the window too."""
    scraper = DiscoveryScraper(
        "serpapi",
        {
            "engine": "google_jobs",
            "query": "rust",
            "parse_mode": "results",
            "max_age_days": 60,
        },
        "K",
    )
    payload = {
        "jobs_results": [
            {
                "title": "Fresh Rust",
                "extensions": ["2 days ago"],
                "apply_options": [{"link": "https://a.example/1"}],
            },
            {
                "title": "Stale Rust",
                "extensions": ["90+ days ago"],
                "apply_options": [{"link": "https://a.example/2"}],
            },
            {
                "title": "Undated Rust",
                "apply_options": [{"link": "https://a.example/3"}],
            },
        ]
    }

    with caplog.at_level(logging.INFO, logger="scrapers.discovery"):
        jobs = scraper.parse(_json_page(payload))
        scraper.normalize(jobs)

    assert [job.title for job in jobs] == ["Fresh Rust", "Undated Rust"]
    # The gate runs outside a sweep too, and reports what it did.
    assert (
        "discovery_age_filter max_age_days=60 stale=1 undated=1 kept=2"
        in caplog.text
    )


async def test_ats_sweep_skips_boards_known_to_be_dead(monkeypatch):
    """A cached 404 must not spend a board slot or a request."""
    import scrapers.discovery as discovery

    dead = "https://api.lever.co/v0/postings/gone?mode=json&limit=100"
    monkeypatch.setattr(discovery, "board_miss_active", lambda url: url == dead)
    scraper = DiscoveryScraper(
        "brave", {"query": "rust", "sweep_ats": True, "max_boards": 2}
    )
    page = _search_results_page(
        [
            "https://jobs.lever.co/gone/1",
            "https://jobs.ashbyhq.com/acme/1",
            "https://jobs.ashbyhq.com/beta/1",
        ]
    )

    urls = await scraper.discover_urls(page)

    # Both live boards fit in a budget the dead one would have spent.
    assert urls == [
        "https://api.ashbyhq.com/posting-api/job-board/acme",
        "https://api.ashbyhq.com/posting-api/job-board/beta",
    ]
    # It still counts as offered: `offered` measures the index, not our cache.
    assert len(scraper._offered_keys) == 3
    assert len(scraper._board_providers) == 2


async def test_ats_sweep_parks_a_board_that_answers_404(monkeypatch, caplog):
    """Only 404/410 are cached; a 500 is retried on the next run."""
    import scrapers.discovery as discovery

    marked: list[str] = []
    # The autouse fixture no-ops the cache; this test watches the writes.
    monkeypatch.setattr(discovery, "board_miss_mark", marked.append)
    scraper = DiscoveryScraper("brave", {"query": "rust", "sweep_ats": True})
    board = resolve_ats_board("https://jobs.lever.co/gone/1")
    assert board is not None
    url = scraper._register_board(board)
    provider = scraper._board_for(url)
    assert provider is not None

    status = {"code": 404}

    async def fake_fetch(fetch_url, *, auth=None):
        raise httpx.HTTPStatusError(
            str(status["code"]),
            request=httpx.Request("GET", fetch_url),
            response=httpx.Response(status["code"]),
        )

    monkeypatch.setattr(provider, "fetch", fake_fetch)

    with caplog.at_level(logging.WARNING, logger="scrapers.discovery"):
        page = await scraper.fetch(url)

    assert page.html_content == ""
    assert marked == [url]
    assert "ats_board_dead url=" in caplog.text

    status["code"] = 500
    assert (await scraper.fetch(url)).html_content == ""
    assert marked == [url]


def test_max_age_days_zero_keeps_every_posting():
    scraper = DiscoveryScraper(
        "serpapi",
        {
            "engine": "google_jobs",
            "query": "rust",
            "parse_mode": "results",
            "max_age_days": 0,
        },
        "K",
    )
    payload = {
        "jobs_results": [
            {
                "title": "Old Rust",
                "extensions": ["2 years ago"],
                "apply_options": [{"link": "https://a.example/1"}],
            }
        ]
    }

    assert len(scraper.parse(_json_page(payload))) == 1
    assert scraper._stale_dropped == 0


async def test_ats_sweep_stops_once_the_job_budget_is_spent():
    """No point paying for boards whose jobs the ``max_jobs`` cap would drop."""
    scraper = DiscoveryScraper(
        "brave",
        {"queries": ["rust a", "rust b"], "sweep_ats": True, "max_jobs": 1},
    )
    board = resolve_ats_board("https://jobs.ashbyhq.com/acme/1")
    assert board is not None
    board_url = scraper._register_board(board)
    page = ScrapedPage(
        html_content=json.dumps(
            {
                "jobs": [
                    {
                        "id": "1",
                        "title": "Rust Engineer",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                    },
                    {
                        "id": "2",
                        "title": "Rust Engineer II",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/2",
                    },
                ]
            }
        ),
        status_code=200,
        final_url=board_url,
    )

    assert len(scraper.parse(page)) == 1  # the cap
    assert scraper.next_page_url(_search_results_page([])) is None
    later = _search_results_page(["https://jobs.lever.co/x/1"])
    assert await scraper.discover_urls(later) == []


async def test_ats_sweep_stops_once_its_time_budget_is_spent():
    scraper = DiscoveryScraper(
        "brave",
        {
            "queries": ["rust a", "rust b"],
            "sweep_ats": True,
            "sweep_max_seconds": 60,
        },
    )
    page = _search_results_page(["https://jobs.ashbyhq.com/acme/1"])
    assert scraper.next_page_url(page)

    scraper._started -= 61
    assert scraper.next_page_url(page) is None
    assert await scraper.discover_urls(page) == []


async def test_ats_sweep_uses_a_shorter_cooldown_for_board_apis():
    """Board APIs are read once per run, from a single host."""
    scraper = DiscoveryScraper("brave", {"query": "rust", "sweep_ats": True})
    assert (
        scraper.rate_limit_seconds_for("https://api.search.brave.com/res/v1/web", 30)
        == 30
    )
    board_url = (
        await scraper.discover_urls(
            _search_results_page(["https://jobs.lever.co/acme/1"])
        )
    )[0]
    assert scraper.rate_limit_seconds_for(board_url, 30) == 3

    tuned = DiscoveryScraper(
        "brave", {"query": "rust", "sweep_ats": True, "board_rate_limit_seconds": 10}
    )
    tuned_board = (
        await tuned.discover_urls(
            _search_results_page(["https://jobs.lever.co/acme/1"])
        )
    )[0]
    assert tuned.rate_limit_seconds_for(tuned_board, 30) == 10


# --- board rotation and deferred drain --------------------------------------
# A sweep offers far more boards than `max_boards` affords (~170 vs 50 in the
# audited run). Before rotation, the boards that lost that race lost it every
# run, so their postings were missed for as long as they stayed open.


class _StubBoardProvider:
    """Board provider whose fetch succeeds or fails on demand."""

    def __init__(self, error: Exception | None = None):
        self.error = error

    async def fetch(self, url: str, **kwargs) -> ScrapedPage:
        if self.error is not None:
            raise self.error
        return ScrapedPage(html_content="{}", status_code=200, final_url=url)


async def test_ats_sweep_rotation_reads_the_least_recently_seen_boards_first(
    monkeypatch,
):
    """Never read, then due again, then recently read — relevance breaks ties.

    Without this the 3-day window buys nothing: the index keeps offering the
    same boards and the same ones keep winning the budget.
    """
    import time as time_module

    import scrapers.discovery as discovery

    now = time_module.time()
    fresh = "https://api.lever.co/v0/postings/fresh?mode=json&limit=100"
    stale = "https://api.ashbyhq.com/posting-api/job-board/stale"
    monkeypatch.setattr(
        discovery,
        "board_last_seen",
        lambda source_id, url: {fresh: now - 3600, stale: now - 10 * 86400}.get(url),
    )
    scraper = DiscoveryScraper(
        "brave",
        {"query": "golang", "sweep_ats": True, "max_boards": 3},
        source_id="src-1",
    )
    page = _search_results_page(
        [
            "https://jobs.lever.co/fresh/1",
            "https://jobs.ashbyhq.com/unread/1",
            "https://jobs.ashbyhq.com/stale/1",
        ]
    )

    urls = await scraper.discover_urls(page)

    assert urls == [
        "https://api.ashbyhq.com/posting-api/job-board/unread",
        stale,
        fresh,
    ]


async def test_ats_sweep_rotation_outranks_snippet_relevance(monkeypatch):
    """An unread board is read before a fresh one with a stronger snippet.

    Relevance used to be the primary sort key, so a board whose snippet matched
    the query kept winning the budget every run while boards the index ranked
    lower were never read — the 3-day window bought nothing. Rotation decides
    first; the snippet only orders boards inside the same bucket.
    """
    import time as time_module

    import scrapers.discovery as discovery

    unread = "https://api.ashbyhq.com/posting-api/job-board/unread"
    fresh = "https://api.ashbyhq.com/posting-api/job-board/fresh"
    now = time_module.time()
    monkeypatch.setattr(
        discovery,
        "board_last_seen",
        lambda source_id, url: now if url == fresh else None,
    )
    scraper = DiscoveryScraper(
        "brave",
        {
            "query": "rust",
            "sweep_ats": True,
            "keywords": ["rust"],
            "locations": ["brazil"],
            "max_boards": 2,
        },
        source_id="src-1",
    )
    page = _json_page(
        {
            "web": {
                "results": [
                    {
                        "url": "https://jobs.ashbyhq.com/fresh/1",
                        "title": "Rust engineer",
                        "description": "rust tokio, remote from brazil",
                    },
                    {
                        "url": "https://jobs.ashbyhq.com/unread/1",
                        "title": "Careers",
                        "description": "",
                    },
                ]
            }
        }
    )

    urls = await scraper.discover_urls(page)

    assert urls == [unread, fresh]


async def test_ats_sweep_snippet_relevance_orders_boards_in_one_bucket(monkeypatch):
    """Inside a bucket the score still ranks: it is a tie-break, not a filter."""
    import scrapers.discovery as discovery

    monkeypatch.setattr(discovery, "board_last_seen", lambda source_id, url: None)
    scraper = DiscoveryScraper(
        "brave",
        {
            "query": "rust",
            "sweep_ats": True,
            "keywords": ["rust"],
            "locations": ["brazil"],
            "max_boards": 2,
        },
        source_id="src-1",
    )
    page = _json_page(
        {
            "web": {
                "results": [
                    {
                        "url": "https://jobs.ashbyhq.com/plain/1",
                        "title": "Careers",
                        "description": "",
                    },
                    {
                        "url": "https://jobs.ashbyhq.com/relevant/1",
                        "title": "Rust engineer",
                        "description": "rust tokio, remote from brazil",
                    },
                ]
            }
        }
    )

    urls = await scraper.discover_urls(page)

    assert urls == [
        "https://api.ashbyhq.com/posting-api/job-board/relevant",
        "https://api.ashbyhq.com/posting-api/job-board/plain",
    ]


async def test_ats_sweep_rotation_never_hides_a_board(monkeypatch):
    """Rotation is a permutation, not a filter: every board is still offered."""
    import time as time_module

    import scrapers.discovery as discovery

    fresh = "https://api.ashbyhq.com/posting-api/job-board/fresh"
    monkeypatch.setattr(
        discovery,
        "board_last_seen",
        lambda source_id, url: time_module.time() if url == fresh else None,
    )
    scraper = DiscoveryScraper(
        "brave",
        {"query": "golang", "sweep_ats": True, "max_boards": 5},
        source_id="src-1",
    )

    urls = await scraper.discover_urls(
        _search_results_page(
            ["https://jobs.ashbyhq.com/fresh/1", "https://jobs.ashbyhq.com/new/1"]
        )
    )

    assert set(urls) == {fresh, "https://api.ashbyhq.com/posting-api/job-board/new"}
    assert len(urls) == 2


@pytest.mark.parametrize(
    ("source_id", "reread_days"),
    [(None, None), ("src-1", 0)],
    ids=["no_source_id", "rotation_disabled"],
)
async def test_ats_sweep_without_rotation_keeps_the_index_order(
    monkeypatch, source_id, reread_days
):
    """No source id (tests, previews) or ``board_reread_days: 0`` = no lookups.

    Rotation must be opt-outable and must never be the reason a backend-only
    deployment needs Redis.
    """
    import scrapers.discovery as discovery

    def _no_lookup(*args, **kwargs):  # pragma: no cover - fails the test if used
        raise AssertionError("rotation must not touch board memory")

    monkeypatch.setattr(discovery, "board_last_seen", _no_lookup)
    config = {"query": "golang", "sweep_ats": True, "max_boards": 5}
    if reread_days is not None:
        config["board_reread_days"] = reread_days
    scraper = DiscoveryScraper("brave", config, source_id=source_id)

    urls = await scraper.discover_urls(
        _search_results_page(
            ["https://jobs.ashbyhq.com/one/1", "https://jobs.ashbyhq.com/two/1"]
        )
    )

    assert urls == [
        "https://api.ashbyhq.com/posting-api/job-board/one",
        "https://api.ashbyhq.com/posting-api/job-board/two",
    ]


async def test_ats_sweep_remembers_a_board_only_after_a_successful_read(monkeypatch):
    """A failed fetch must not count as reviewed: the board stays at the front.

    Marking on registration instead of on success would rotate broken boards as
    if they had been read, which is exactly how a board's postings go missing.
    """
    import scrapers.discovery as discovery

    marked: list[tuple[str, str]] = []
    monkeypatch.setattr(
        discovery,
        "board_mark_seen",
        lambda source_id, url, **kwargs: marked.append((source_id, url)),
    )
    forgotten: list[tuple[str, str]] = []
    monkeypatch.setattr(
        discovery,
        "board_forget",
        lambda source_id, url: forgotten.append((source_id, url)),
    )
    scraper = DiscoveryScraper(
        "brave", {"query": "golang", "sweep_ats": True}, source_id="src-1"
    )
    board_url = "https://api.ashbyhq.com/posting-api/job-board/acme"
    request = httpx.Request("GET", board_url)

    def _http_error(status: int) -> httpx.HTTPStatusError:
        return httpx.HTTPStatusError(
            "boom", request=request, response=httpx.Response(status, request=request)
        )

    scraper._board_providers[board_url] = _StubBoardProvider(error=_http_error(500))
    failed = await scraper.fetch(board_url)
    assert failed.status_code == 0
    assert marked == []
    # A 500 says nothing about the board: keep its place in the rotation.
    assert forgotten == []

    # A board that is gone is not "recently read": forget it, so a re-registered
    # URL starts at the front of the queue.
    scraper._board_providers[board_url] = _StubBoardProvider(error=_http_error(404))
    await scraper.fetch(board_url)
    assert marked == []
    assert forgotten == [("src-1", board_url)]

    scraper._board_providers[board_url] = _StubBoardProvider()
    await scraper.fetch(board_url)
    assert marked == [("src-1", board_url)]


async def test_ats_sweep_parks_what_the_share_cannot_afford_and_drains_it(caplog):
    """A board the per-query share parked is read when the budget is left over.

    Measured on the audited sweep: the equal share left a query with slots it
    never used while ~90 offered boards went unread. Parking them and draining
    afterwards spends the budget instead of dropping the boards.
    """
    scraper = DiscoveryScraper(
        "brave",
        {
            "queries": ["q1", "q2"],
            "sweep_ats": True,
            "max_boards": 4,
            "min_boards_per_query": 0,
        },
    )

    with caplog.at_level(logging.INFO, logger="scrapers.discovery"):
        first = _query_page("a")
        urls = await scraper.discover_urls(first)
        assert len(urls) == 2  # half of the budget, the other half reserved
        # q2 offers nothing: its reserved slots would go unspent.
        assert scraper.next_page_url(first) is not None
        assert await scraper.discover_urls(_search_results_page([])) == []
        drained = scraper.drain_urls()
        scraper.normalize([])

    assert (
        "ats_sweep_query query=q1 offered=4 read=2 blocked=2 dead=0" in caplog.text
    )

    assert drained == [
        "https://api.ashbyhq.com/posting-api/job-board/a2",
        "https://api.ashbyhq.com/posting-api/job-board/a3",
    ]
    assert (
        "ats_sweep_deferred registered=2 parked=2 dead=0 blocked=0 boards=4"
        in caplog.text
    )
    # Parked once: draining twice must not re-read or double-count.
    assert scraper.drain_urls() == []


async def test_ats_sweep_drain_stops_at_the_board_budget(caplog):
    """The drained boards still obey ``max_boards`` (one slot left, two parked)."""
    scraper = DiscoveryScraper(
        "brave",
        {
            "queries": ["q1", "q2"],
            "sweep_ats": True,
            "max_boards": 3,
            "min_boards_per_query": 0,
        },
    )

    with caplog.at_level(logging.INFO, logger="scrapers.discovery"):
        first = _query_page("a")
        await scraper.discover_urls(first)
        scraper.next_page_url(first)
        await scraper.discover_urls(_search_results_page([]))
        drained = scraper.drain_urls()

    assert drained == ["https://api.ashbyhq.com/posting-api/job-board/a2"]
    assert (
        "ats_sweep_deferred registered=1 parked=2 dead=0 blocked=1 boards=3"
        in caplog.text
    )


async def test_ats_sweep_reaches_every_offered_board_across_runs(monkeypatch):
    """Rotation turns a bounded per-run budget into eventual coverage.

    160 boards offered, 40 read per run: without rotation the same 40 were read
    every day and the other 120 never were. Each run now moves the read boards
    back, so four runs cover the whole index — and a posting only has to be
    live for one of them to be stored (``_store_jobs`` dedupes per source).
    """
    import time as time_module

    import scrapers.discovery as discovery

    store: dict[str, float] = {}
    monkeypatch.setattr(
        discovery, "board_last_seen", lambda source_id, url: store.get(url)
    )
    monkeypatch.setattr(
        discovery,
        "board_mark_seen",
        lambda source_id, url, **kwargs: store.__setitem__(url, time_module.time()),
    )

    async def _offline_board_fetch(self, url: str, *, auth=None) -> ScrapedPage:
        return ScrapedPage(html_content="{}", status_code=200, final_url=url)

    monkeypatch.setattr(discovery.AshbyProvider, "fetch", _offline_board_fetch)

    offered = 160
    per_run = 40
    page = _json_page(
        {
            "web": {
                "results": [
                    {"url": f"https://jobs.ashbyhq.com/org{index}/1"}
                    for index in range(offered)
                ]
            }
        }
    )
    read: set[str] = set()
    first_run: set[str] = set()
    for run in range(4):
        scraper = DiscoveryScraper(
            "brave",
            {
                "query": "golang",
                "sweep_ats": True,
                "max_boards": per_run,
                "min_boards_per_query": 0,
            },
            source_id="src-1",
        )
        urls = await scraper.discover_urls(page)
        urls += scraper.drain_urls()
        assert len(urls) == per_run
        for url in urls:
            await scraper.fetch(url)
        if run == 0:
            first_run = set(urls)
        read.update(urls)

    assert len(read) == offered
    # Four runs, disjoint quarters: run 2 is not a repeat of run 1.
    assert len(first_run) == per_run and len(store) == offered


def test_ats_sweep_caps_one_board_contribution_with_max_jobs_per_board(caplog):
    """``max_jobs_per_board`` limits how much of a run one board can eat."""
    scraper = DiscoveryScraper(
        "brave",
        {
            "query": "golang",
            "sweep_ats": True,
            "keywords": ["golang"],
            "max_jobs_per_board": 2,
        },
    )
    board = resolve_ats_board("https://jobs.ashbyhq.com/acme/1")
    assert board is not None
    board_url = scraper._register_board(board)
    payload = {
        "jobs": [
            {
                "id": str(index),
                "title": f"Golang Engineer {index}",
                "jobUrl": f"https://jobs.ashbyhq.com/acme/{index}",
                "descriptionHtml": "<p>Golang services</p>",
            }
            for index in range(5)
        ]
    }
    page = ScrapedPage(
        html_content=json.dumps(payload), status_code=200, final_url=board_url
    )

    with caplog.at_level(logging.INFO, logger="scrapers.discovery"):
        jobs = scraper.parse(page)

    assert [job.external_id for job in jobs] == ["0", "1"]
    assert f"ats_sweep_board_capped url={board_url} kept=5 cap=2" in caplog.text


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


async def test_fetch_html_posts_a_form_body_when_asked(monkeypatch, offline_fetch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text='{"success": true, "data": {"html": ""}}')

    _patch_httpx_transport(monkeypatch, handler)
    page = await fetch_html(
        _OFFLINE_URL,
        method="POST",
        form_body={"action": "filter_vacancies_v2_loadmore", "page": "0"},
    )

    assert page.status_code == 200
    request = seen[0]
    assert request.method == "POST"
    # A PHP endpoint reads `$_POST`: the fields must be form-encoded, and no
    # JSON body may ride along (WordPress answers a bare `0` to one).
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert request.content == b"action=filter_vacancies_v2_loadmore&page=0"


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


async def test_fetch_html_accepts_a_caller_size_cap(monkeypatch, offline_fetch):
    """ATS board dumps pass their own cap; the page default would reject them."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="x" * 5000)

    _patch_httpx_transport(monkeypatch, handler)
    monkeypatch.setattr(utils.settings, "scraper_max_response_bytes", 100)

    with pytest.raises(ValueError, match="scraper_max_response_bytes"):
        await fetch_html(_OFFLINE_URL)

    page = await fetch_html(_OFFLINE_URL, max_bytes=10_000)
    assert len(page.html_content) == 5000


async def test_ats_providers_fetch_boards_with_the_larger_size_cap(monkeypatch):
    """A board JSON is bigger than a page, so the provider raises the cap."""
    import scrapers.discovery as discovery

    seen: list[int | None] = []

    async def fake_fetch_html(url, *, auth=None, max_bytes=None):
        seen.append(max_bytes)
        return ScrapedPage(html_content="{}", status_code=200, final_url=url)

    monkeypatch.setattr(discovery, "fetch_html", fake_fetch_html)
    url = "https://api.ashbyhq.com/posting-api/job-board/openai"
    page = await AshbyProvider({"org": "openai"}).fetch(url)

    assert page.final_url == url
    assert seen == [AshbyProvider.max_response_bytes]
    assert AshbyProvider.max_response_bytes > utils.settings.scraper_max_response_bytes


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


def test_search_api_providers_require_a_key_only_when_known_missing():
    """Creation stays possible; a known-missing key fails with an actionable error."""
    assert BraveProvider.validate_config({"query": "rust"}, has_api_key=None) is None
    assert BraveProvider.validate_config({"query": "rust"}, has_api_key=True) is None
    with pytest.raises(ValueError, match="needs an API key"):
        BraveProvider.validate_config({"query": "rust"}, has_api_key=False)


async def test_brave_fetch_surfaces_the_validation_error_body(monkeypatch, offline_fetch):
    """Brave explains a rejected request in the payload (e.g. missing header)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Subscription-Token"] == "brave-secret-key"
        return httpx.Response(
            422,
            json={"error": {"detail": "missing x-subscription-token"}},
        )

    _patch_httpx_transport(monkeypatch, handler)
    provider = BraveProvider({"query": "rust remote"}, "brave-secret-key")

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        await provider.fetch(provider.results_url())

    assert "missing x-subscription-token" in str(excinfo.value)
    assert "brave-secret-key" not in str(excinfo.value)


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
