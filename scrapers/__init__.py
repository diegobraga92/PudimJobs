"""Scraper implementations, one class per source type.

A scraper is responsible for turning a ``Source`` URL into a list of
normalized, ready-to-insert job dicts. See ``base.py`` for the contract.
"""

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
