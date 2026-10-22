"""Career page scraper."""

from scrapers.base import AbstractScraper
from scrapers.types import FetchAuth, RawJob, ScrapedPage
from scrapers.utils import fetch_html, parse_job_detail, parse_json_ld_jobs


class CareerPageScraper(AbstractScraper):
    """Generic scraper for static company career pages."""

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        return await fetch_html(url, auth=auth)

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        # Preferred: schema.org JSON-LD JobPosting blocks.
        json_ld_jobs = parse_json_ld_jobs(page.html_content, page.final_url)
        if json_ld_jobs:
            return json_ld_jobs

        # Fallback: common CSS selectors (single-listing page assumption).
        return parse_job_detail(page)

    def normalize(self, raw_jobs: list[RawJob]) -> list[dict]:
        return [
            {
                "title": raw.title.strip(),
                "company": raw.company.strip() or "Unknown",
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
