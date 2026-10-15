"""Manual (watchlist) source: a board the engine cannot scrape.

Sources of type ``manual`` are never fetched by the sweeper — this scraper
exists only so the registry has a class to hand out, keeping
``get_scraper`` total over every :class:`SourceType`. ``parse`` and
``normalize`` return nothing, and ``fetch`` refuses loudly: no reachable code
path may call it (``POST /sources/preview`` short-circuits with an explanation
and the scrape task skips manual sources before touching the registry), so a
raise here is a bug in the caller, not a user-facing error.
"""

from scrapers.base import AbstractScraper
from scrapers.types import FetchAuth, RawJob, ScrapedPage


class ManualScraper(AbstractScraper):
    """No-op scraper for hand-checked watchlist sources."""

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        raise RuntimeError(
            "manual sources are not fetched automatically; open the URL by hand"
        )

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        return []

    def normalize(self, raw_jobs: list[RawJob]) -> list[dict]:
        return []
