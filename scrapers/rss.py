"""RSS/Atom feed scraper.

Parses job feeds with ``feedparser``. Feed entries map to ``RawJob`` and the
feed's title/company metadata supplies the company name when entries lack one.
"""

from datetime import UTC, datetime

import feedparser

from scrapers.base import AbstractScraper
from scrapers.types import FetchAuth, RawJob, ScrapedPage
from scrapers.utils import fetch_html


def _entry_date(entry) -> object | None:
    published = entry.get("published_parsed") or entry.get("updated_parsed")
    if published:
        return datetime(*published[:6], tzinfo=UTC).date()
    return None


class RSSScraper(AbstractScraper):
    """Scraper for RSS/Atom job feeds (e.g. Greenhouse, Lever, custom feeds)."""

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        return await fetch_html(url, timeout=30.0, auth=auth)

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        parsed = feedparser.parse(page.html_content)
        feed_company = parsed.feed.get("title", "").strip()
        jobs: list[RawJob] = []
        for entry in parsed.entries:
            summary = entry.get("summary", "")
            jobs.append(
                RawJob(
                    title=entry.get("title", "").strip(),
                    company=feed_company,
                    url=entry.get("link"),
                    posted_date=_entry_date(entry),
                    description=summary,
                    external_id=entry.get("id"),
                )
            )
        return jobs

    def normalize(self, raw_jobs: list[RawJob]) -> list[dict]:
        return [
            {
                "title": raw.title,
                "company": raw.company or "Unknown",
                "description": raw.description,
                "url": raw.url,
                "posted_date": raw.posted_date,
                "tags": raw.tags or [],
                "external_id": raw.external_id,
            }
            for raw in raw_jobs
            if raw.title and raw.title.strip() and raw.url
        ]
