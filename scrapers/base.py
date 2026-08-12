"""Scraper base class and contract."""

from abc import ABC, abstractmethod

from scrapers.types import FetchAuth, RawJob, ScrapedPage


class AbstractScraper(ABC):
    """Contract every scraper must implement.

    ``fetch`` is async (network I/O); ``parse`` and ``normalize`` are sync
    (CPU-bound parsing with BeautifulSoup/feedparser). ``fetch`` accepts an
    optional ``FetchAuth`` for login-required sources.
    """

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
        """Turn raw listings into dicts ready for ``Job`` insertion.

        Keys should match ``app.models.Job`` columns: title, company,
        description, url, posted_date, tags.
        """
