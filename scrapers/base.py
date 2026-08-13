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

    async def discover_urls(self, page: ScrapedPage) -> list[str]:
        """Return job *detail* URLs found on a listing/search page.

        Single-page scrapers return ``[]`` (the default), in which case the
        scrape task treats ``parse()`` as the job source for that page.
        Discovery sources (search engines / ATS boards) override this to return
        result links, which the scrape task then fetches and parses individually.
        """
        return []

    def first_fetch_url(self, source_url: str) -> str:
        """The URL fetched on the first page of a run (default: the source URL).

        Discovery providers override this to return their provider-built
        endpoint (e.g. a search API URL carrying the API key).
        """
        return source_url
