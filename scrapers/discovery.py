"""Discovery providers: search-engine and ATS-board job sources.

A ``discovery`` source turns a *query* (or an ATS board) into job postings via
a pluggable provider, selected per-source with ``sources.config["provider"]``.

Providers come in two families:

- ``ats``         — fetch a board's public JSON endpoint and parse jobs directly
                    (one stage).
- ``search_api``  — query a search API (needs an encrypted API key), extract
                    result links, then fetch + parse each job detail page
                    (two stages).

Each provider exposes the standard scraper pieces — ``fetch``, ``parse``,
``normalize`` — plus the two-stage hooks ``discover_urls`` (links on a results
page) and ``next_page_url`` (results pagination). ``DiscoveryScraper`` wraps a
provider so the registry can dispatch it like any other scraper.
"""

import json
from abc import ABC, abstractmethod
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from scrapers.base import AbstractScraper
from scrapers.types import FetchAuth, RawJob, ScrapedPage
from scrapers.utils import fetch_html, parse_job_detail, parse_json_ld_jobs


def _date_prefix(value: object) -> str | None:
    """Return the ``YYYY-MM-DD`` prefix of an ISO timestamp/date (or None)."""
    if not value:
        return None
    return str(value)[:10]


def _strip_html(html: str | None) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True)


def _location_name(location: object) -> str:
    """Normalize ATS location payloads (string, or ``{city, country}`` dict)."""
    if isinstance(location, dict):
        parts = [str(v) for v in (location.get("city"), location.get("country")) if v]
        if parts:
            return " ".join(parts).strip()
        return str(location.get("name") or "").strip()
    return str(location or "").strip()


def _tags(*values: object) -> list[str]:
    return [str(v) for v in values if v]


class DiscoveryProvider(ABC):
    """Base class for all discovery providers."""

    provider_name: str = ""
    family: str = ""  # "ats" | "search_api"
    requires_key: bool = False

    def __init__(self, config: dict | None = None, api_key: str | None = None):
        self.config = config or {}
        self.api_key = api_key

    @abstractmethod
    def results_url(self) -> str:
        """The first results/feed URL for this source."""
        raise NotImplementedError

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        return await fetch_html(url, auth=auth)

    def discover_urls(self, page: ScrapedPage) -> list[str]:
        """Extract job *detail* URLs from a results page (two-stage providers)."""
        return []

    @abstractmethod
    def parse(self, page: ScrapedPage) -> list[RawJob]:
        raise NotImplementedError

    def next_page_url(self, page: ScrapedPage) -> str | None:
        """The next results page URL, or None (default: single page)."""
        return None

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


class ATSProvider(DiscoveryProvider):
    """One-stage provider: a board's public JSON endpoint yields jobs directly."""

    family = "ats"
    endpoint_tpl: str = ""

    def results_url(self) -> str:
        try:
            return self.endpoint_tpl.format(**self.config)
        except KeyError as exc:
            raise ValueError(
                f"{self.provider_name} requires a '{exc.args[0]}' entry in source config"
            ) from exc

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        data = json.loads(page.html_content)
        jobs = self._jobs_from_payload(data)
        max_results = int(self.config.get("max_results") or 0)
        if max_results > 0:
            jobs = jobs[:max_results]
        return jobs

    def _jobs_from_payload(self, data: object) -> list[RawJob]:
        raise NotImplementedError


class AshbyProvider(ATSProvider):
    provider_name = "ashby"
    endpoint_tpl = "https://api.ashbyhq.com/posting-api/job-board/{org}"

    def _jobs_from_payload(self, data):
        jobs: list[RawJob] = []
        for item in data.get("jobs", []):
            description = item.get("descriptionHtml")
            jobs.append(
                RawJob(
                    title=item.get("title") or "",
                    company=self.config.get("company") or self.config.get("org") or "",
                    url=item.get("jobUrl") or item.get("url"),
                    posted_date=_date_prefix(item.get("publishedAt")),
                    description=_strip_html(description) or None,
                    tags=_tags(item.get("department"), item.get("employmentType")),
                )
            )
        return [j for j in jobs if j.title and j.url]


class GreenhouseProvider(ATSProvider):
    provider_name = "greenhouse"
    endpoint_tpl = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"

    def _jobs_from_payload(self, data):
        jobs: list[RawJob] = []
        for item in data.get("jobs", []):
            location = _location_name(item.get("location"))
            description = _strip_html(item.get("content"))
            jobs.append(
                RawJob(
                    title=item.get("title") or "",
                    company=self.config.get("company")
                    or self.config.get("board_token")
                    or "",
                    url=item.get("absolute_url"),
                    posted_date=_date_prefix(item.get("updated_at")),
                    description=description[:2000] if description else None,
                    tags=_tags(location) if location else [],
                )
            )
        return [j for j in jobs if j.title and j.url]


class LeverProvider(ATSProvider):
    provider_name = "lever"
    endpoint_tpl = "https://api.lever.co/v0/postings/{company}?mode=json"

    def _jobs_from_payload(self, data):
        jobs: list[RawJob] = []
        for item in data or []:
            cats = item.get("categories") or {}
            description = (
                item.get("descriptionPlain") or _strip_html(item.get("description"))
            )[:2000] or None
            jobs.append(
                RawJob(
                    title=item.get("text") or "",
                    company=self.config.get("company") or "",
                    url=item.get("hostedUrl"),
                    posted_date=_date_prefix(item.get("createdAt")),
                    description=description,
                    tags=_tags(
                        cats.get("commitment"),
                        cats.get("location"),
                        item.get("workplaceType"),
                    ),
                )
            )
        return [j for j in jobs if j.title and j.url]


class WorkableProvider(ATSProvider):
    provider_name = "workable"
    endpoint_tpl = "https://apply.workable.com/api/v3/accounts/{org}/jobs"

    def _jobs_from_payload(self, data):
        jobs: list[RawJob] = []
        for item in data.get("jobs", []):
            location = _location_name(item.get("location"))
            description = (item.get("description") or "")[:2000] or None
            jobs.append(
                RawJob(
                    title=item.get("title") or "",
                    company=self.config.get("company") or self.config.get("org") or "",
                    url=item.get("url"),
                    posted_date=_date_prefix(
                        item.get("published_on") or item.get("published_at")
                    ),
                    description=description,
                    tags=_tags(location) if location else [],
                )
            )
        return [j for j in jobs if j.title and j.url]


class TwoStageProvider(DiscoveryProvider):
    """Search-based provider: results page → links → fetch each detail page."""

    def discover_urls(self, page: ScrapedPage) -> list[str]:
        return self.result_links(page)

    def result_links(self, page: ScrapedPage) -> list[str]:
        raise NotImplementedError

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        """Parse a job *detail* page (JSON-LD first, CSS selectors fallback)."""
        strategy = self.config.get("detail_strategy", "json_ld")
        if strategy != "selectors":
            jobs = parse_json_ld_jobs(page.html_content)
            if jobs:
                return jobs
        return parse_job_detail(page, self.config.get("selectors"))

    def _next_offset(self, page: ScrapedPage) -> int | None:
        return None

    def next_page_url(self, page: ScrapedPage) -> str | None:
        next_offset = self._next_offset(page)
        if not next_offset:
            return None
        if hasattr(self, "_offset"):
            self._offset = int(next_offset)
        return self.build_results_url(int(next_offset))

    def build_results_url(self, offset: int | None = None) -> str:
        raise NotImplementedError


class SearchApiProvider(TwoStageProvider):
    """Two-stage provider backed by an official search API (needs a key)."""

    family = "search_api"
    requires_key = True
    key_header: str | None = None

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        if self.key_header and self.api_key:
            headers = dict((auth.headers or {}) if auth else {})
            headers[self.key_header] = self.api_key
            return await fetch_html(url, auth=FetchAuth(headers=headers))
        return await fetch_html(url, auth=auth)

    def results_url(self) -> str:
        return self.build_results_url()


class GoogleCseProvider(SearchApiProvider):
    provider_name = "google_cse"

    def build_results_url(self, offset: int | None = None) -> str:
        params = {
            "key": self.api_key or "",
            "cx": self.config.get("cx", ""),
            "q": self.config.get("query", ""),
        }
        if offset:
            params["start"] = offset
        return "https://www.googleapis.com/customsearch/v1?" + urlencode(params)

    def result_links(self, page: ScrapedPage) -> list[str]:
        data = json.loads(page.html_content)
        return [item.get("link") for item in data.get("items", []) if item.get("link")]

    def _next_offset(self, page: ScrapedPage) -> int | None:
        data = json.loads(page.html_content)
        next_page = data.get("queries", {}).get("nextPage", [])
        if next_page:
            return int(next_page[0].get("startIndex") or 0) or None
        return None


class BingProvider(SearchApiProvider):
    provider_name = "bing"
    key_header = "Ocp-Apim-Subscription-Key"

    def __init__(self, config: dict | None = None, api_key: str | None = None):
        super().__init__(config, api_key)
        self._offset = 0

    def build_results_url(self, offset: int | None = None) -> str:
        params = {
            "q": self.config.get("query", ""),
            "count": int(self.config.get("count") or 10),
        }
        if offset:
            params["offset"] = offset
        return "https://api.bing.microsoft.com/v7.0/search?" + urlencode(params)

    def result_links(self, page: ScrapedPage) -> list[str]:
        data = json.loads(page.html_content)
        return [
            item.get("url")
            for item in data.get("webPages", {}).get("value", [])
            if item.get("url")
        ]

    def _next_offset(self, page: ScrapedPage) -> int | None:
        data = json.loads(page.html_content)
        total = (data.get("webPages") or {}).get("totalEstimatedMatches") or 0
        per_page = int(self.config.get("count") or 10)
        nxt = self._offset + per_page
        if total and nxt >= int(total):
            return None
        return nxt


class BraveProvider(SearchApiProvider):
    provider_name = "brave"
    key_header = "X-Subscription-Token"

    def build_results_url(self, offset: int | None = None) -> str:
        params = {
            "q": self.config.get("query", ""),
            "count": int(self.config.get("count") or 10),
        }
        if offset:
            params["offset"] = offset
        return "https://api.search.brave.com/res/v1/web/search?" + urlencode(params)

    def result_links(self, page: ScrapedPage) -> list[str]:
        data = json.loads(page.html_content)
        return [
            item.get("url")
            for item in data.get("web", {}).get("results", [])
            if item.get("url")
        ]

    def _next_offset(self, page: ScrapedPage) -> int | None:
        data = json.loads(page.html_content)
        return data.get("web", {}).get("next_offset")


class SerpApiProvider(SearchApiProvider):
    """Third-party search API covering LinkedIn Jobs / Indeed / Google Jobs.

    SerpApi returns structured JSON (``jobs_results``) for the configured
    ``engine`` (``linkedin_jobs``, ``indeed``, ``google_jobs``); the API key is
    sent as the ``api_key`` query param and billed per search query — an
    explicit opt-in via the encrypted key.
    """

    provider_name = "serpapi"

    def build_results_url(self, offset: int | None = None) -> str:
        params = {
            "api_key": self.api_key or "",
            "engine": self.config.get("engine", "google_jobs"),
            "q": self.config.get("query", ""),
        }
        if self.config.get("location"):
            params["location"] = self.config["location"]
        if self.config.get("num"):
            params["num"] = self.config["num"]
        if offset:
            params["start"] = offset
        return "https://serpapi.com/search?" + urlencode(params)

    def result_links(self, page: ScrapedPage) -> list[str]:
        data = json.loads(page.html_content)
        links: list[str] = []
        for item in data.get("jobs_results", []):
            for key in ("link", "job_google_link", "apply_link", "url", "share_link"):
                value = item.get(key)
                if value:
                    links.append(value)
                    break
        return links

    def next_page_url(self, page: ScrapedPage) -> str | None:
        data = json.loads(page.html_content)
        return (data.get("serpapi_pagination") or {}).get("next")


class BrightDataProvider(SearchApiProvider):
    """Bright Data Web Unlocker / SERP API: renders the target search page.

    The API key is sent as ``Authorization: Bearer`` and the target search URL
    is POSTed as JSON to ``api.brightdata.com/serp/req``, returning *rendered*
    HTML. Result links are extracted with per-engine CSS selectors (overridable
    via ``result_selector`` in the source config). Bright Data's exact endpoint
    and params should be confirmed against their current docs; they are
    config-adjustable (``customer``, ``zone``, ``country``, ``locale``).
    """

    provider_name = "brightdata"
    key_header = "Authorization"

    def _target_url(self) -> str:
        """The LinkedIn/Indeed search URL Bright Data renders for us."""
        engine = self.config.get("engine", "linkedin")
        query = self.config.get("query", "")
        location = self.config.get("location", "")
        if engine == "indeed":
            params = urlencode({k: v for k, v in {"q": query, "l": location}.items() if v})
            return f"https://br.indeed.com/jobs?{params}"
        params = urlencode(
            {k: v for k, v in {"keywords": query, "location": location}.items() if v}
        )
        return f"https://www.linkedin.com/jobs/search?{params}"

    def build_results_url(self, offset: int | None = None) -> str:
        params = {
            "customer": self.config.get("customer", ""),
            "zone": self.config.get("zone", ""),
        }
        return "https://api.brightdata.com/serp/req?" + urlencode(params)

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: dict = {"url": self._target_url(), "format": "raw"}
        if self.config.get("country"):
            payload["country"] = self.config["country"]
        if self.config.get("locale"):
            payload["locale"] = self.config["locale"]
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return ScrapedPage(
                html_content=resp.text,
                status_code=resp.status_code,
                final_url=url,
            )

    def result_links(self, page: ScrapedPage) -> list[str]:
        soup = BeautifulSoup(page.html_content, "lxml")
        selector = self.config.get("result_selector") or self._default_selector()
        links: list[str] = []
        for node in soup.select(selector):
            href = node.get("href") if hasattr(node, "get") else None
            if href:
                links.append(str(href))
        return links

    def _default_selector(self) -> str:
        if self.config.get("engine") == "indeed":
            return "h2.jobTitle a"
        return "a[href*='/jobs/view']"


DISCOVERY_PROVIDERS: dict[str, type[DiscoveryProvider]] = {
    cls.provider_name: cls
    for cls in (
        AshbyProvider,
        GreenhouseProvider,
        LeverProvider,
        WorkableProvider,
        GoogleCseProvider,
        BingProvider,
        BraveProvider,
        SerpApiProvider,
        BrightDataProvider,
    )
}


def get_discovery_provider(
    name: str, config: dict | None = None, api_key: str | None = None
) -> DiscoveryProvider:
    """Instantiate the discovery provider registered under ``name``."""
    try:
        provider_cls = DISCOVERY_PROVIDERS[name]
    except KeyError as exc:
        raise ValueError(f"No discovery provider registered for {name!r}") from exc
    return provider_cls(config, api_key)


class DiscoveryScraper(AbstractScraper):
    """Adapter exposing a ``DiscoveryProvider`` through the scraper contract."""

    def __init__(
        self,
        provider_name: str,
        config: dict | None = None,
        api_key: str | None = None,
    ):
        self.provider = get_discovery_provider(provider_name, config, api_key)

    def first_fetch_url(self, source_url: str) -> str:
        return self.provider.results_url()

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        return await self.provider.fetch(url, auth=auth)

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        return self.provider.parse(page)

    async def discover_urls(self, page: ScrapedPage) -> list[str]:
        return self.provider.discover_urls(page)

    def next_page_url(self, page: ScrapedPage) -> str | None:
        return self.provider.next_page_url(page)

    def normalize(self, raw_jobs: list[RawJob]) -> list[dict]:
        return self.provider.normalize(raw_jobs)
