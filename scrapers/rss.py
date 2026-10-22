"""RSS/Atom feed scraper."""

import re
from datetime import UTC, datetime

import feedparser
from bs4 import BeautifulSoup

from scrapers.base import AbstractScraper
from scrapers.types import FetchAuth, RawJob, ScrapedPage
from scrapers.utils import as_flag, as_tag_list, fetch_html

# Feeds such as We Work Remotely put the employer in the title
# ("Acme Corp: Senior Rust Engineer") and the channel title is the board, not
# the company.
_COMPANY_TITLE_RE = re.compile(r"^(?P<company>[^:]{1,80}):\s+(?P<title>.+)$")

# NoDesk uses the opposite title shape ("Senior Rust Engineer at Acme Corp").
# Split on the *last* " at " so a title containing "at" keeps its words.
_TITLE_AT_RE = re.compile(r"\s+at\s+", re.IGNORECASE)

# Jobspresso puts the employer and location in the entry author
# ("Acme<br>⚲&nbsp;Brazil"). Keep only the part before the location marker.
_AUTHOR_LOCATION_RE = re.compile(r"⚲|\|")

# Category terms that describe a location/arrangement rather than a skill.
_REGION_RE = re.compile(
    r"\b(?:remote|worldwide|anywhere|americas?|latam|latin america|"
    r"south america|north america|europe|asia|africa|oceania|brazil|brasil|"
    r"portugal|canada|usa|united states|uk|apac|emea)\b",
    re.IGNORECASE,
)


def _entry_date(entry) -> object | None:
    published = entry.get("published_parsed") or entry.get("updated_parsed")
    if published:
        return datetime(*published[:6], tzinfo=UTC).date()
    return None


def _entry_categories(entry) -> list[str]:
    """Term strings from feedparser's ``tags`` payload (dicts or strings)."""
    terms: list[str] = []
    for tag in entry.get("tags") or []:
        term = tag.get("term") if isinstance(tag, dict) else tag
        if term and str(term).strip():
            terms.append(str(term).strip())
    return terms


class RSSScraper(AbstractScraper):
    """Scraper for RSS/Atom job feeds (e.g. Greenhouse, Lever, custom feeds).

    Optional ``config`` flags handle feeds whose metadata is shaped around the
    board rather than the employer:

    - ``company_from_title``: split ``"Company: Job title"`` titles.
    - ``company_from_title_at``: split ``"Job title at Company"`` titles.
    - ``company_from_author``: use the entry author as the employer, dropping
      any location marker Jobspresso appends to it (only the company is dropped;
      the reading becomes ``RawJob.location``).
    - ``include_categories``: add every feed category to ``tags``.
    - ``include_region``: add region-like categories (and an explicit
      ``region``/``location`` entry field) to ``tags`` and to the detected
      location.
    - ``strip_html``: turn an HTML summary into plain text.

    The flags are opt-in so existing feeds keep their current rows.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        return await fetch_html(url, timeout=30.0, auth=auth)

    def _company_from_author(self, entry) -> str | None:
        """The employer in an entry author, without Jobspresso's location suffix."""
        text = self._author_text(entry)
        if not text:
            return None
        # Authors can contain markup (`Acme<br>⚲&nbsp;Brazil`); a newline
        # separator keeps `<br>` boundaries, then the first line is the company.
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        company = _AUTHOR_LOCATION_RE.split(first_line, maxsplit=1)[0].strip()
        return company or None

    @staticmethod
    def _author_text(entry) -> str | None:
        """The entry author as plain text (markup kept as line boundaries)."""
        author = entry.get("author")
        if not author:
            authors = entry.get("authors") or []
            if authors and isinstance(authors[0], dict):
                author = authors[0].get("name")
        if not author:
            return None
        return BeautifulSoup(str(author), "lxml").get_text("\n", strip=True)

    def _author_location(self, entry) -> str | None:
        """The location Jobspresso appends to the author (``Algolia ⚲ Brazil``)."""
        text = self._author_text(entry)
        if not text:
            return None
        for line in text.splitlines():
            parts = _AUTHOR_LOCATION_RE.split(line, maxsplit=1)
            if len(parts) < 2:
                continue
            location = parts[1].replace("\xa0", " ").strip()
            if location:
                return location
        return None

    def _location(self, entry) -> str | None:
        """The posting's detected location, from the fields a feed may carry.

        RSS has no standard location element, so the practical sources are the
        explicit ``region``/``location`` fields some boards add, region-like
        categories (only when ``include_region`` opts in), and the location
        suffix Jobspresso puts in the author.
        """
        parts: list[str] = []
        for key in ("region", "location"):
            parts.extend(as_tag_list(entry.get(key)))
        if as_flag(self.config.get("include_region")):
            parts.extend(
                category
                for category in _entry_categories(entry)
                if _REGION_RE.search(category)
            )
        author_location = self._author_location(entry)
        if author_location:
            parts.append(author_location)
        return ", ".join(dict.fromkeys(parts)) or None

    @staticmethod
    def _company_from_title_at(title: str) -> tuple[str, str] | None:
        """Split ``"Job title at Company"`` on the last ``at`` separator."""
        matches = list(_TITLE_AT_RE.finditer(title))
        if not matches:
            return None
        match = matches[-1]
        job_title = title[: match.start()].strip()
        company = title[match.end() :].strip()
        if not job_title or not company:
            return None
        return job_title, company

    def _title_and_company(self, entry, feed_company: str) -> tuple[str, str]:
        title = entry.get("title", "").strip()
        company = feed_company
        if as_flag(self.config.get("company_from_title")):
            match = _COMPANY_TITLE_RE.match(title)
            if match:
                title = match.group("title").strip()
                company = match.group("company").strip()
        elif as_flag(self.config.get("company_from_title_at")):
            split = self._company_from_title_at(title)
            if split:
                title, company = split
        if as_flag(self.config.get("company_from_author")):
            author_company = self._company_from_author(entry)
            if author_company:
                company = author_company
        return title, company

    def _description(self, entry) -> str | None:
        summary = entry.get("summary") or entry.get("description") or ""
        if not summary:
            return None
        if as_flag(self.config.get("strip_html")):
            return BeautifulSoup(summary, "lxml").get_text(" ", strip=True) or None
        return summary

    def _tags(self, entry) -> list[str]:
        categories = _entry_categories(entry)
        tags: list[str] = []
        if as_flag(self.config.get("include_categories")):
            tags.extend(categories)
        if as_flag(self.config.get("include_region")):
            tags.extend(category for category in categories if _REGION_RE.search(category))
            for key in ("region", "location"):
                tags.extend(as_tag_list(entry.get(key)))
        # Preserve feed order while removing duplicates.
        return list(dict.fromkeys(tags))

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        parsed = feedparser.parse(page.html_content)
        feed_company = parsed.feed.get("title", "").strip()
        jobs: list[RawJob] = []
        for entry in parsed.entries:
            title, company = self._title_and_company(entry, feed_company)
            jobs.append(
                RawJob(
                    title=title,
                    company=company,
                    url=entry.get("link"),
                    posted_date=_entry_date(entry),
                    description=self._description(entry),
                    tags=self._tags(entry),
                    location=self._location(entry),
                    external_id=entry.get("id"),
                )
            )
        return jobs

    def normalize(self, raw_jobs: list[RawJob]) -> list[dict]:
        return [
            {
                "title": raw.title,
                "company": raw.company or "Unknown",
                "description": raw.description,
                "url": raw.url,
                "posted_date": raw.posted_date,
                "tags": raw.tags or [],
                "location": raw.location,
                "external_id": raw.external_id,
            }
            for raw in raw_jobs
            if raw.title and raw.title.strip() and raw.url
        ]
