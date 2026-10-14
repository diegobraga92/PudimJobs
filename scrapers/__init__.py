"""Scraper implementations, one class per source type."""

from scrapers.aggregator import AggregatorScraper
from scrapers.base import AbstractScraper
from scrapers.career_page import CareerPageScraper
from scrapers.rss import RSSScraper

__all__ = [
    "AbstractScraper",
    "AggregatorScraper",
    "CareerPageScraper",
    "RSSScraper",
]
