"""Registry mapping source types to scraper classes."""

from app.models.enums import SourceType
from scrapers.aggregator import (
    AggregatorScraper,
    GenericHtmlListScraper,
    get_aggregator_adapter,
)
from scrapers.base import AbstractScraper
from scrapers.career_page import CareerPageScraper
from scrapers.discovery import DiscoveryScraper
from scrapers.rss import RSSScraper

SCRAPER_REGISTRY: dict[SourceType, type[AbstractScraper]] = {
    SourceType.career_page: CareerPageScraper,
    SourceType.aggregator: AggregatorScraper,
    SourceType.rss: RSSScraper,
    SourceType.discovery: DiscoveryScraper,
}


def get_scraper(source, api_key: str | None = None) -> AbstractScraper:
    """Instantiate the scraper registered for a source.

    Aggregator sources are dispatched to the adapter named in
    ``source.config["adapter"]`` (default ``generic_html_list``). Discovery
    sources are dispatched to the provider named in
    ``source.config["provider"]`` and receive the source's encrypted API key
    (used by search-API providers).
    """
    try:
        scraper_cls = SCRAPER_REGISTRY[source.type]
    except KeyError as exc:
        raise ValueError(f"No scraper registered for source type {source.type!r}") from exc
    if source.type == SourceType.aggregator:
        config = source.config or {}
        adapter = config.get("adapter", GenericHtmlListScraper.adapter_name)
        return get_aggregator_adapter(adapter, config)
    if source.type == SourceType.discovery:
        config = source.config or {}
        provider = config.get("provider")
        if not provider:
            raise ValueError("discovery source requires a 'provider' entry in config")
        return DiscoveryScraper(provider, config, api_key)
    return scraper_cls()
