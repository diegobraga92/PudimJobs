"""Aggregator scraper.

Base implementation for job-board aggregators (Indeed, LinkedIn, ...). The
base class raises ``NotImplementedError`` — concrete adapters will be added
per aggregator. Aggregators typically need per-site selectors and anti-bot
handling, so each adapter is developed and tested against a fixture.
"""

from scrapers.base import AbstractScraper
from scrapers.types import RawJob, ScrapedPage
from scrapers.utils import fetch_html


class AggregatorScraper(AbstractScraper):
    """Base scraper for aggregator sites (to be subclassed per site)."""

    async def fetch(self, url: str) -> ScrapedPage:
        return await fetch_html(url)

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        raise NotImplementedError(
            "AggregatorScraper is a base class; use a concrete adapter "
            "(e.g. IndeedScraper, LinkedInScraper)."
        )

    def normalize(self, raw_jobs: list[RawJob]) -> list[dict]:
        raise NotImplementedError(
            "AggregatorScraper is a base class; use a concrete adapter."
        )
