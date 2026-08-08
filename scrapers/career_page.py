"""Career page scraper.

Parses HTML from company career pages. Strategy:
1. JSON-LD ``application/ld+json`` blocks with ``@type: JobPosting``
   (the most reliable structured format).
2. Fallback to common CSS selectors used by static career pages.
"""

import json
import re
from datetime import date

from bs4 import BeautifulSoup

from scrapers.base import AbstractScraper
from scrapers.types import RawJob, ScrapedPage
from scrapers.utils import fetch_html

_TITLE_SELECTORS = ["h1[class*='job']", "h2[class*='job']", "h1", "h2", "[data-job-title]"]
_COMPANY_SELECTORS = ["[data-company]", ".company", ".employer", "meta[name='company']"]
_LOCATION_SELECTORS = ["[data-location]", ".location", ".job-location"]
_DESCRIPTION_SELECTORS = ["[data-job-description]", ".description", ".job-description", "#job-description"]
_DATE_SELECTORS = ["[data-posted-date]", "time[datetime]", ".date", ".posted-date"]


def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            if node.name == "meta":
                return node.get("content")
            text = node.get_text(" ", strip=True)
            if text:
                return text
    return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    iso = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if iso:
        try:
            return date.fromisoformat(iso.group())
        except ValueError:
            return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


class CareerPageScraper(AbstractScraper):
    """Generic scraper for static company career pages."""

    async def fetch(self, url: str) -> ScrapedPage:
        return await fetch_html(url)

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        soup = BeautifulSoup(page.html_content, "lxml")

        # Preferred: schema.org JSON-LD JobPosting blocks.
        json_ld_jobs = self._parse_json_ld(soup)
        if json_ld_jobs:
            return json_ld_jobs

        # Fallback: common CSS selectors (single-listing page assumption).
        title = _first_text(soup, _TITLE_SELECTORS)
        company = _first_text(soup, _COMPANY_SELECTORS)
        if company is None and soup.find("meta", attrs={"name": "company"}):
            company = soup.find("meta", attrs={"name": "company"}).get("content")
        if not title or not company:
            return []
        description = _first_text(soup, _DESCRIPTION_SELECTORS)
        posted_date = _parse_date(_first_text(soup, _DATE_SELECTORS))

        return [
            RawJob(
                title=title,
                company=company or "",
                url=page.final_url,
                posted_date=posted_date,
                description=description,
            )
        ]

    def _parse_json_ld(self, soup: BeautifulSoup) -> list[RawJob]:
        jobs: list[RawJob] = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, AttributeError):
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                    continue
                jobs.append(self._raw_from_json_ld(item))
        return jobs

    def _raw_from_json_ld(self, item: dict) -> RawJob:
        title = item.get("title") or ""
        company_obj = item.get("hiringOrganization") or {}
        company = company_obj.get("name") if isinstance(company_obj, dict) else ""
        tags = [tag for tag in (item.get("skills") or []) if isinstance(tag, str)]
        return RawJob(
            title=title,
            company=company or "",
            url=item.get("url") or item.get("@id"),
            posted_date=_parse_date(item.get("datePosted")),
            description=item.get("description"),
            tags=tags,
            external_id=item.get("identifier"),
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
