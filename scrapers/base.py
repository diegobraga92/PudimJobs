"""Scraper base class and contract."""

from abc import ABC, abstractmethod

from scrapers.types import FetchAuth, RawJob, ScrapedPage


class AbstractScraper(ABC):
    """Contract every scraper must implement."""

    @abstractmethod
    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        """Fetch the source URL and return the raw page."""

    @abstractmethod
    def parse(self, page: ScrapedPage) -> list[RawJob]:
        """Parse a page into raw job listings."""

    @abstractmethod
    def normalize(self, raw_jobs: list[RawJob]) -> list[dict]:
        """Turn raw listings into dicts ready for ``Job`` insertion."""

    async def discover_urls(self, page: ScrapedPage) -> list[str]:
        """Return job *detail* URLs found on a listing/search page."""
        return []

    def first_fetch_url(self, source_url: str) -> str:
        """The URL fetched on the first page of a run (default: the source URL)."""
        return source_url
