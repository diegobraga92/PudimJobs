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
    - ``include_categories``: add every feed category to ``tags``.
    - ``include_region``: add region-like categories (and an explicit
      ``region``/``location`` entry field) to ``tags``.
    - ``strip_html``: turn an HTML summary into plain text.

    The flags are opt-in so existing feeds keep their current rows.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        return await fetch_html(url, timeout=30.0, auth=auth)

    def _title_and_company(self, entry, feed_company: str) -> tuple[str, str]:
        title = entry.get("title", "").strip()
        if not as_flag(self.config.get("company_from_title")):
            return title, feed_company
        match = _COMPANY_TITLE_RE.match(title)
        if not match:
            return title, feed_company
        return match.group("title").strip(), match.group("company").strip()

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
                "external_id": raw.external_id,
            }
            for raw in raw_jobs
            if raw.title and raw.title.strip() and raw.url
        ]
