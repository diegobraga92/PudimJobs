"""Aggregator scrapers: job boards that list many jobs on one page.

Adapters are registered in ``AGGREGATOR_ADAPTERS`` and selected per-source via
``sources.config["adapter"]`` (default ``generic_html_list``). The base class
provides ``fetch`` (auth + SSRF-guarded) and ``normalize``; each adapter
implements ``parse`` and optionally ``next_page_url`` for pagination.
"""

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import AbstractScraper
from scrapers.types import FetchAuth, RawJob, ScrapedPage
from scrapers.utils import fetch_html


class AggregatorScraper(AbstractScraper):
    """Base class for aggregator adapters."""

    adapter_name = "base"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        return await fetch_html(url, auth=auth)

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        raise NotImplementedError(
            f"AggregatorScraper adapter {self.adapter_name!r} does not implement parse()"
        )

    def normalize(self, raw_jobs: list[RawJob]) -> list[dict]:
        return [
            {
                "title": raw.title.strip(),
                "company": raw.company.strip() or "Unknown",
                "description": raw.description,
                "url": raw.url,
                "posted_date": raw.posted_date,
                "tags": raw.tags or [],
            }
            for raw in raw_jobs
            if raw.title and raw.url
        ]

    def next_page_url(self, page: ScrapedPage) -> str | None:
        """Return the next listing page URL, or None when there is no next page."""
        return None


class GenericHtmlListScraper(AggregatorScraper):
    """CSS-selector-driven list scraper for static job boards.

    Reads selectors from ``Source.config``::

        {
          "adapter": "generic_html_list",
          "item_selector": "li.job",
          "title_selector": "h2",
          "url_selector": "a",
          "company_selector": ".company",
          "location_selector": ".location",
          "date_selector": "time",
          "next_page_selector": "a.next",
          "max_pages": 3
        }
    """

    adapter_name = "generic_html_list"

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        soup = BeautifulSoup(page.html_content, "lxml")
        items = soup.select(self.config.get("item_selector", "article"))
        jobs: list[RawJob] = []
        for item in items:
            title_node = item.select_one(self.config.get("title_selector", "h2"))
            url_node = item.select_one(self.config.get("url_selector", "a"))
            company_node = item.select_one(
                self.config.get("company_selector", ".company")
            )
            location_node = item.select_one(
                self.config.get("location_selector", ".location")
            )

            title = title_node.get_text(" ", strip=True) if title_node else None
            url = url_node.get("href") if url_node else None
            if not title or not url:
                continue
            full_url = urljoin(page.final_url, url)
            company = company_node.get_text(" ", strip=True) if company_node else None
            location = location_node.get_text(" ", strip=True) if location_node else None
            description = f"Location: {location}" if location else None
            jobs.append(
                RawJob(
                    title=title,
                    company=company or "",
                    url=full_url,
                    description=description,
                )
            )
        return jobs

    def next_page_url(self, page: ScrapedPage) -> str | None:
        selector = self.config.get("next_page_selector")
        if not selector:
            return None
        soup = BeautifulSoup(page.html_content, "lxml")
        node = soup.select_one(selector)
        href = node.get("href") if node else None
        return urljoin(page.final_url, href) if href else None


AGGREGATOR_ADAPTERS: dict[str, type[AggregatorScraper]] = {
    GenericHtmlListScraper.adapter_name: GenericHtmlListScraper,
}


def get_aggregator_adapter(
    name: str, config: dict | None = None
) -> AggregatorScraper:
    """Instantiate the aggregator adapter registered under ``name``."""
    try:
        scraper_cls = AGGREGATOR_ADAPTERS[name]
    except KeyError as exc:
        raise ValueError(f"No aggregator adapter registered for {name!r}") from exc
    return scraper_cls(config)

