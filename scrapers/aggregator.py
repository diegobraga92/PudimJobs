"""Aggregator scrapers: job boards that list many jobs on one page."""

import json
import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import AbstractScraper
from scrapers.types import FetchAuth, RawJob, ScrapedPage
from scrapers.utils import (
    as_optional_str,
    as_tag_list,
    coerce_date,
    fetch_html,
    parse_job_detail,
    parse_json_ld_jobs,
    resolve_path,
)


def _flag(value: object) -> bool:
    """Interpret a config flag that may arrive as a bool or a JSON string."""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _text(soup: BeautifulSoup, selector: object) -> str | None:
    """Trimmed text of the first match for ``selector`` (or ``None``)."""
    if not selector or not isinstance(selector, str):
        return None
    node = soup.select_one(selector)
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    return text or None


def _date_from_node(node: object) -> date | None:
    """A date from a ``<time datetime=...>`` node, falling back to its text."""
    if node is None or not hasattr(node, "get_text"):
        return None
    raw = None
    if hasattr(node, "has_attr") and node.has_attr("datetime"):
        raw = node.get("datetime")
    return coerce_date(raw) or coerce_date(node.get_text(" ", strip=True))


class AggregatorScraper(AbstractScraper):
    """Base class for aggregator adapters."""

    adapter_name = "base"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        return await fetch_html(url, auth=auth)

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        raise NotImplementedError(
            f"AggregatorScraper adapter {self.adapter_name!r} does not implement parse()"
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
                "external_id": raw.external_id,
            }
            for raw in raw_jobs
            if raw.title and raw.title.strip() and raw.url
        ]

    def next_page_url(self, page: ScrapedPage) -> str | None:
        """Return the next listing page URL, or None when there is no next page."""
        return None

    @classmethod
    def config_metadata(cls) -> dict:
        """The adapter's config contract (see ``/api/sources/adapters``)."""
        return _ADAPTER_CONFIG_METADATA.get(
            cls.adapter_name,
            {"required": (), "required_any": (), "optional": (), "example": {}},
        )


class GenericHtmlListScraper(AggregatorScraper):
    """CSS-selector-driven list scraper for static job boards."""

    adapter_name = "generic_html_list"

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        if _flag(self.config.get("detail")):
            return self._parse_detail(page)
        return self._parse_list(page)

    def discover_urls(self, page: ScrapedPage) -> list[str]:
        """Job *detail* URLs for every listing row (only in ``detail`` mode)."""
        if not _flag(self.config.get("detail")):
            return []
        soup = BeautifulSoup(page.html_content, "lxml")
        item_selector = self.config.get("item_selector", "article")
        url_selector = self.config.get("url_selector", "a")
        links: list[str] = []
        for item in soup.select(item_selector):
            node = item.select_one(url_selector)
            href = node.get("href") if node else None
            if href:
                links.append(urljoin(page.final_url, str(href)))
        return links

    def _parse_list(self, page: ScrapedPage) -> list[RawJob]:
        """Parse a listing page into one job per row."""
        soup = BeautifulSoup(page.html_content, "lxml")
        items = soup.select(self.config.get("item_selector", "article"))
        date_selector = self.config.get("date_selector")
        jobs: list[RawJob] = []
        for item in items:
            title_node = item.select_one(self.config.get("title_selector", "h2"))
            url_node = item.select_one(self.config.get("url_selector", "a"))
            company_node = item.select_one(
                self.config.get("company_selector", ".company")
            )
            location_node = item.select_one(
                self.config.get("location_selector", ".location")
            )

            title = title_node.get_text(" ", strip=True) if title_node else None
            url = url_node.get("href") if url_node else None
            if not title or not url:
                continue
            full_url = urljoin(page.final_url, url)
            company = company_node.get_text(" ", strip=True) if company_node else None
            location = location_node.get_text(" ", strip=True) if location_node else None
            description = f"Location: {location}" if location else None
            date_node = item.select_one(date_selector) if date_selector else None
            jobs.append(
                RawJob(
                    title=title,
                    company=company or "",
                    url=full_url,
                    posted_date=_date_from_node(date_node),
                    description=description,
                )
            )
        return jobs

    def _parse_detail(self, page: ScrapedPage) -> list[RawJob]:
        """Parse a job *detail* page (JSON-LD first, then ``detail_*`` selectors)."""
        jobs = parse_json_ld_jobs(page.html_content)
        if jobs:
            return jobs

        title_selector = self.config.get("detail_title_selector") or self.config.get(
            "title_selector"
        )
        selectors = {
            "title_selectors": title_selector,
            "company_selectors": self.config.get("detail_company_selector")
            or self.config.get("company_selector"),
            "location_selectors": self.config.get("detail_location_selector"),
            "description_selectors": self.config.get("detail_description_selector"),
            "date_selectors": self.config.get("detail_date_selector"),
        }
        jobs = parse_job_detail(
            page, {key: value for key, value in selectors.items() if value}
        )
        if jobs:
            return jobs

        # Fallback for boards whose detail page has no company block (typically a
        # company-specific board): keep the job, using the configured `company`
        # name — normalization turns an empty company into "Unknown".
        soup = BeautifulSoup(page.html_content, "lxml")
        title = _text(soup, title_selector or "h1")
        if not title:
            return []
        date_selector = self.config.get("detail_date_selector")
        location = _text(soup, self.config.get("detail_location_selector"))
        description = _text(soup, self.config.get("detail_description_selector"))
        if location:
            description = (
                f"{description} • Location: {location}"
                if description
                else f"Location: {location}"
            )
        return [
            RawJob(
                title=title,
                company=str(self.config.get("company") or ""),
                url=page.final_url,
                posted_date=_date_from_node(
                    soup.select_one(date_selector) if date_selector else None
                ),
                description=description,
            )
        ]

    def next_page_url(self, page: ScrapedPage) -> str | None:
        selector = self.config.get("next_page_selector")
        if not selector:
            return None
        soup = BeautifulSoup(page.html_content, "lxml")
        node = soup.select_one(selector)
        href = node.get("href") if node else None
        return urljoin(page.final_url, href) if href else None


class EmbeddedJsonListScraper(AggregatorScraper):
    """Config-driven adapter for boards that embed their data in the page."""

    adapter_name = "embedded_json_list"

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        payload = self._payload(page)
        items = resolve_path(payload, self.config.get("items_path")) if payload else None
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            jobs = parse_json_ld_jobs(page.html_content)
            if jobs:
                return jobs
            if payload is None:
                return []
            raise ValueError(
                "embedded_json_list: 'items_path' must point to a JSON array "
                f"(got {type(items).__name__})"
            )

        jobs = [
            self._job_from_item(item, page.final_url)
            for item in items
            if isinstance(item, dict)
        ]
        jobs = [job for job in jobs if job.title and job.url]
        max_results = int(self.config.get("max_results") or 0)
        return jobs[:max_results] if max_results > 0 else jobs

    def _payload(self, page: ScrapedPage) -> object | None:
        """The embedded JSON blob, from a script tag or a ``window`` global."""
        script_id = self.config.get("payload_script", "__NEXT_DATA__")
        if script_id:
            soup = BeautifulSoup(page.html_content, "lxml")
            node = soup.find("script", id=str(script_id))
            if node is not None and node.string:
                try:
                    return json.loads(node.string)
                except json.JSONDecodeError:
                    pass
        global_name = self.config.get("payload_global")
        if global_name:
            payload = self._payload_from_global(page.html_content, str(global_name))
            if payload is not None:
                return payload
        return None

    def _payload_from_global(self, text: str, name: str) -> object | None:
        """Decode the JSON assigned to ``window.<name>`` (Nuxt-style blobs)."""
        match = re.search(rf"window\.{re.escape(name)}\s*=\s*", text)
        if not match:
            return None
        start = match.end()
        while start < len(text) and text[start].isspace():
            start += 1
        try:
            value, _ = json.JSONDecoder().raw_decode(text, start)
        except json.JSONDecodeError:
            return None
        return value

    def _job_from_item(self, item: dict, base_url: str) -> RawJob:
        def field(key: str) -> object:
            path = self.config.get(key)
            if not path:
                return None
            return resolve_path(item, path)

        url = as_optional_str(field("url_path"))
        if url and self.config.get("url_tpl"):
            context = {key: str(value) for key, value in self.config.items()}
            context["url"] = url
            try:
                url = str(self.config["url_tpl"]).format(**context)
            except (KeyError, IndexError, ValueError) as exc:
                raise ValueError(
                    "embedded_json_list url_tpl could not be rendered: "
                    f"{str(self.config['url_tpl'])!r} ({exc})"
                ) from exc

        location = as_optional_str(field("location_path"))
        tags = as_tag_list(field("tags_path"))
        if location:
            tags.append(location)

        raw_description = field("description_path")
        description = None
        if raw_description:
            description = str(raw_description)[:2000] or None

        return RawJob(
            title=str(field("title_path") or "").strip(),
            company=str(field("company_path") or "").strip()
            or str(self.config.get("company") or ""),
            url=urljoin(base_url, url) if url else None,
            posted_date=coerce_date(field("date_path")),
            description=description,
            tags=tags,
            external_id=as_optional_str(field("id_path")),
        )


_ADAPTER_CONFIG_METADATA: dict[str, dict] = {
    "generic_html_list": {
        "required": (),
        "required_any": (),
        "optional": (
            "item_selector",
            "title_selector",
            "url_selector",
            "company_selector",
            "location_selector",
            "date_selector",
            "next_page_selector",
            "detail",
            "detail_title_selector",
            "detail_company_selector",
            "detail_description_selector",
            "detail_location_selector",
            "detail_date_selector",
            "company",
            "max_pages",
            "max_results",
        ),
        "example": {
            "item_selector": "li.job",
            "title_selector": "h2",
            "url_selector": "a",
            "company_selector": ".company",
            "location_selector": ".location",
            "next_page_selector": "a.next",
        },
    },
    "embedded_json_list": {
        "required": (),
        "required_any": (("items_path",),),
        "optional": (
            "payload_script",
            "payload_global",
            "id_path",
            "title_path",
            "url_path",
            "url_tpl",
            "company_path",
            "company",
            "location_path",
            "date_path",
            "tags_path",
            "description_path",
            "max_results",
        ),
        "example": {
            "payload_script": "__NEXT_DATA__",
            "items_path": "props.pageProps.jobs",
            "title_path": "title",
            "url_path": "slug",
        },
    },
}


AGGREGATOR_ADAPTERS: dict[str, type[AggregatorScraper]] = {
    GenericHtmlListScraper.adapter_name: GenericHtmlListScraper,
    EmbeddedJsonListScraper.adapter_name: EmbeddedJsonListScraper,
}


def get_aggregator_adapter(
    name: str, config: dict | None = None
) -> AggregatorScraper:
    """Instantiate the aggregator adapter registered under ``name``."""
    try:
        scraper_cls = AGGREGATOR_ADAPTERS[name]
    except KeyError as exc:
        raise ValueError(f"No aggregator adapter registered for {name!r}") from exc
    return scraper_cls(config)

