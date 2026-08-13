"""Shared data structures for scrapers."""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone


@dataclass
class ScrapedPage:
    """The outcome of fetching a page."""

    html_content: str
    status_code: int
    final_url: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RawJob:
    """A job listing as extracted by a parser (pre-normalization)."""

    title: str
    company: str
    url: str | None = None
    posted_date: date | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    external_id: str | None = None


@dataclass
class FetchAuth:
    """Optional authentication context for an outbound scraper fetch.

    Either ``headers`` (e.g. ``{"Authorization": "Bearer ..."}``) or ``api_key``
    (an opaque API key whose *placement* — query param or header — is up to the
    scraper/provider that consumes it) can be set.
    """

    headers: dict[str, str] | None = None
    api_key: str | None = None

