"""Unit tests for the scraper implementations (no DB/network required)."""


from scrapers.career_page import CareerPageScraper
from scrapers.rss import RSSScraper
from scrapers.types import ScrapedPage

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


def test_rss_normalize_drops_entries_without_link():
    scraper = RSSScraper()
    raw = scraper.parse(_page(RSS_FEED))
    normalized = scraper.normalize(raw)
    assert len(normalized) == 2
    assert all(item["url"] for item in normalized)
