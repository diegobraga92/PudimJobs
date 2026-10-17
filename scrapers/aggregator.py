"""Aggregator scrapers: job boards that list many jobs on one page."""

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import AbstractScraper
from scrapers.types import FetchAuth, RawJob, ScrapedPage
from scrapers.utils import (
    as_flag,
    as_optional_str,
    as_tag_list,
    coerce_date,
    date_from_node,
    fetch_html,
    parse_html_list,
    parse_job_detail,
    parse_json_ld_jobs,
    resolve_path,
)


def _text(soup: BeautifulSoup, selector: object) -> str | None:
    """Trimmed text of the first match for ``selector`` (or ``None``)."""
    if not selector or not isinstance(selector, str):
        return None
    node = soup.select_one(selector)
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    return text or None


def _render_context(config: dict, page: int) -> dict:
    """Template values for ``url_tpl``/``next_page_tpl``: config keys + ``page``.

    Every config key is available (stringified), so a search term or a locale
    kept in the config reaches the template. ``page`` is reserved and set last,
    mirroring how ``JsonListProvider`` renders its own templates.
    """
    context = {key: str(value) for key, value in config.items()}
    context["page"] = page
    return context


def _render_tpl(adapter: str, key: str, tpl: object, context: dict) -> str:
    """Render a URL template, naming the template when a placeholder is unknown."""
    try:
        return str(tpl).format(**context)
    except (KeyError, IndexError, ValueError) as exc:
        raise ValueError(
            f"{adapter} could not render {key!r} {str(tpl)!r}: {exc}"
        ) from exc


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

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        #: Pages walked so far, so `next_page_tpl` can render ``{page}``.
        self._page = 1

    def first_fetch_url(self, source_url: str) -> str:
        """The URL fetched first: the stored URL, or its ``url_tpl`` when set.

        A board whose listing depends on a search term can keep the *term* in the
        config and the URL in ``url_tpl``, so page 1 and ``next_page_tpl`` (whose
        ``{page}`` starts at 2) render from the same values instead of drifting
        apart — one source then covers any term. Without ``url_tpl`` the stored
        URL is fetched **verbatim**, so arguments already in it (``?palabra=Rust``,
        ``/vagas-de-emprego/rust``) keep working untouched.
        """
        tpl = self.config.get("url_tpl")
        if not tpl:
            return source_url
        return _render_tpl(
            self.adapter_name, "url_tpl", tpl, _render_context(self.config, 1)
        )

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        if as_flag(self.config.get("detail")):
            return self._parse_detail(page)
        return self._parse_list(page)

    def discover_urls(self, page: ScrapedPage) -> list[str]:
        """Job *detail* URLs for every listing row (only in ``detail`` mode)."""
        if not as_flag(self.config.get("detail")):
            return []
        soup = BeautifulSoup(page.html_content, "lxml")
        item_selector = self.config.get("item_selector", "article")
        url_selector = self.config.get("url_selector", "a")
        links: list[str] = []
        for item in soup.select(item_selector):
            node = item.select_one(url_selector)
            if node is None and item.name == "a":
                # The row *is* the link (`a.position-row` on dev.pro): soupsieve
                # has no `:scope`, so read the href off the row itself.
                node = item
            href = node.get("href") if node else None
            if href:
                links.append(urljoin(page.final_url, str(href)))
        return links

    def _parse_list(self, page: ScrapedPage) -> list[RawJob]:
        """Parse a listing page into one job per row (shared helper in utils)."""
        return parse_html_list(page, self.config)

    def _parse_detail(self, page: ScrapedPage) -> list[RawJob]:
        """Parse a job *detail* page (JSON-LD first, then ``detail_*`` selectors)."""
        jobs = parse_json_ld_jobs(page.html_content, page.final_url)
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
                posted_date=date_from_node(
                    soup.select_one(date_selector) if date_selector else None
                ),
                description=description,
            )
        ]

    def next_page_url(self, page: ScrapedPage) -> str | None:
        """The next listing page: the ``next_page_selector`` link, else a built URL.

        A *link* wins when the selector is set — a real ``?page=2`` anchor also
        disappears on the last page, so the walk ends by itself. Boards that page
        through a query string without such an anchor use ``next_page_tpl``
        instead: the URL is **built** (``{page}`` starts at 2; page 1 is the
        source URL) and gated by ``max_pages``, exactly like ``embedded_json_list``.
        """
        selector = self.config.get("next_page_selector")
        if selector:
            soup = BeautifulSoup(page.html_content, "lxml")
            node = soup.select_one(selector)
            href = node.get("href") if node else None
            return urljoin(page.final_url, href) if href else None

        tpl = self.config.get("next_page_tpl")
        if not tpl:
            return None
        max_pages = int(self.config.get("max_pages") or 1)
        if self._page + 1 > max_pages:
            return None
        self._page += 1
        context = _render_context(self.config, self._page)
        # A relative template (`?page={page}`) resolves against the page we are
        # on, so one config works on any locale host.
        return urljoin(
            page.final_url,
            _render_tpl(self.adapter_name, "next_page_tpl", tpl, context),
        )


class EmbeddedJsonListScraper(AggregatorScraper):
    """Config-driven adapter for boards that embed their data in the page."""

    adapter_name = "embedded_json_list"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._page = 1

    def next_page_url(self, page: ScrapedPage) -> str | None:
        """Pagination for ``next_page_tpl`` configs (``{page}`` starts at 2).

        Boards that render their listing with a JS framework usually page through
        a query string (``?page=2``) instead of a *link*, so the next URL is
        **built** from the template rather than read off the page — the opposite
        of ``generic_html_list``'s ``next_page_selector``. The first page is the
        source URL itself; ``max_pages`` (read by the worker too, and therefore
        required for this to do anything) caps the walk.
        """
        tpl = self.config.get("next_page_tpl")
        if not tpl:
            return None
        max_pages = int(self.config.get("max_pages") or 1)
        if self._page + 1 > max_pages:
            return None
        self._page += 1
        context = _render_context(self.config, self._page)
        # Built URLs resolve against the page we are on, so a relative template
        # (`?page={page}`) works and an absolute one is returned untouched.
        return urljoin(
            page.final_url,
            _render_tpl(self.adapter_name, "next_page_tpl", tpl, context),
        )

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        payload = self._payload(page)
        items = resolve_path(payload, self.config.get("items_path")) if payload else None
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            jobs = parse_json_ld_jobs(page.html_content, page.final_url)
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
            context = _render_context(self.config, self._page)
            context["url"] = url
            url = _render_tpl(
                self.adapter_name, "url_tpl", self.config["url_tpl"], context
            )

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
            "description_selector",
            "next_page_selector",
            "next_page_tpl",
            "url_tpl",
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
            "next_page_tpl",
            "max_pages",
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

