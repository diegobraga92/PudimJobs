"""Registry mapping source types to scraper classes."""

from app.models.enums import SourceType

from scrapers.aggregator import AggregatorScraper
from scrapers.base import AbstractScraper
from scrapers.career_page import CareerPageScraper
from scrapers.rss import RSSScraper

SCRAPER_REGISTRY: dict[SourceType, type[AbstractScraper]] = {
    SourceType.career_page: CareerPageScraper,
    SourceType.aggregator: AggregatorScraper,
    SourceType.rss: RSSScraper,
}


def get_scraper(source_type: SourceType) -> AbstractScraper:
    """Instantiate the scraper registered for ``source_type``."""
    try:
        scraper_cls = SCRAPER_REGISTRY[source_type]
    except KeyError as exc:
        raise ValueError(f"No scraper registered for source type {source_type!r}") from exc
    return scraper_cls()
