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
    #: Detected location of the posting ("Remote - Brazil", "Sao Paulo, SP").
    #: Kept apart from ``tags`` so the per-source ``locations`` filter and the
    #: jobs UI can rely on it; ``None`` means the board did not report one.
    location: str | None = None
    external_id: str | None = None
    #: Text the local keyword/location filters match when it differs from what
    #: is worth storing. A board dump carries the whole posting body and the
    #: tech stack often sits past the stored 2 KB, so Greenhouse matches the
    #: full text while `description` keeps what the app shows. Never stored.
    match_text: str | None = None


@dataclass
class FetchAuth:
    """Optional authentication context for an outbound scraper fetch."""

    headers: dict[str, str] | None = None
    api_key: str | None = None

