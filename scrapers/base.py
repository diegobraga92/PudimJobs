"""Scraper base class and contract."""

from abc import ABC, abstractmethod

from scrapers.types import FetchAuth, RawJob, ScrapedPage


class AbstractScraper(ABC):
    """Contract every scraper must implement."""

    #: Fallback for ``config['max_results']``: the number of *paid* detail
    #: fetches a run may make when the source does not set its own cap. Keyed
    #: search providers lower it (see ``DiscoveryProvider.default_max_results``);
    #: an explicit ``max_results`` in the config always wins.
    default_max_results: int = 20

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

    def robots_url(self, fetch_url: str) -> str:
        """The URL whose robots.txt governs a fetch of ``fetch_url``.

        Scrapers that fetch through a third-party renderer (Bright Data)
        override this with the real board URL, so the robots check stays honest.
        """
        return fetch_url

    def check_credentials(self, has_api_key: bool) -> None:
        """Raise ``ValueError`` when this scraper cannot run without a key.

        Called by the scrape task before the first fetch, so a keyed provider
        whose key was never added fails fast with an actionable message instead
        of a vendor 401. Providers that do not need credentials keep this no-op
        (``has_api_key`` is only ever ``False`` here: a stored key is enough).
        """
        return None
