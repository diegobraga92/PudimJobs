"""Discovery providers: search-engine and ATS-board job sources."""

import json
from abc import ABC, abstractmethod
from urllib.parse import urlencode, urljoin
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from scrapers.base import AbstractScraper
from scrapers.types import FetchAuth, RawJob, ScrapedPage
from scrapers.utils import (
    as_optional_str,
    as_tag_list,
    assert_safe_url,
    coerce_date,
    fetch_html,
    parse_job_detail,
    parse_json_ld_jobs,
    resolve_path,
)


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


def _label(container: object) -> str | None:
    """The ``label`` of an ATS facet payload (e.g. ``{"label": "Full-time"}``)."""
    if isinstance(container, dict):
        return as_optional_str(container.get("label"))
    return None


def _xml_text(node: ElementTree.Element, tag: str) -> str | None:
    """Trimmed text of the first ``tag`` child of an XML ``node`` (or None)."""
    found = node.find(tag)
    if found is None or not found.text:
        return None
    text = found.text.strip()
    return text or None


class DiscoveryProvider(ABC):
    """Base class for all discovery providers."""

    provider_name: str = ""
    family: str = ""  # "ats" | "json" | "search_api"
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

    @classmethod
    def config_metadata(cls) -> dict:
        """The provider's config contract, published by ``/api/sources/providers``."""
        return _DISCOVERY_CONFIG_METADATA.get(
            cls.provider_name,
            {"required": (), "required_any": (), "optional": (), "example": {}},
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


class SmartRecruitersProvider(ATSProvider):
    """SmartRecruiters public postings API (``companies/{company}/postings``)."""

    provider_name = "smartrecruiters"
    endpoint_tpl = "https://api.smartrecruiters.com/v1/companies/{company}/postings"

    def results_url(self) -> str:
        """The postings URL, with ``limit`` taken from ``max_results``."""
        limit = int(self.config.get("max_results") or 100)
        return f"{super().results_url()}?limit={limit}"

    def _jobs_from_payload(self, data):
        jobs: list[RawJob] = []
        for item in data.get("content", []):
            company_obj = item.get("company") if isinstance(item.get("company"), dict) else {}
            identifier = company_obj.get("identifier") or self.config.get("company") or ""
            location = item.get("location") if isinstance(item.get("location"), dict) else {}
            jobs.append(
                RawJob(
                    title=item.get("name") or "",
                    company=str(company_obj.get("name") or identifier).strip(),
                    url=(
                        f"https://jobs.smartrecruiters.com/{identifier}/{item.get('id')}"
                        if item.get("id")
                        else None
                    ),
                    posted_date=coerce_date(item.get("releasedDate")),
                    tags=_tags(
                        _label(item.get("typeOfEmployment")),
                        _label(item.get("department")),
                        _label(item.get("function")),
                        location.get("fullLocation"),
                    ),
                    external_id=str(item["id"]) if item.get("id") else None,
                )
            )
        return [j for j in jobs if j.title and j.url]


class RecruiteeProvider(ATSProvider):
    """Recruitee public offers API (``{company}.recruitee.com/api/offers/``)."""

    provider_name = "recruitee"
    endpoint_tpl = "https://{company}.recruitee.com/api/offers/"

    def _jobs_from_payload(self, data):
        jobs: list[RawJob] = []
        for item in data.get("offers", []):
            location = as_optional_str(item.get("city")) or as_optional_str(
                item.get("location")
            )
            country = as_optional_str(item.get("country_code"))
            if location and country:
                location = f"{location}, {country}"

            raw_description = item.get("description")
            description = None
            if raw_description:
                description = _strip_html(str(raw_description))[:2000] or None

            jobs.append(
                RawJob(
                    title=item.get("title") or "",
                    company=item.get("company_name") or self.config.get("company") or "",
                    url=item.get("careers_url") or item.get("careers_apply_url"),
                    posted_date=coerce_date(
                        item.get("created_at") or item.get("published_at")
                    ),
                    description=description,
                    tags=as_tag_list(item.get("tags"))
                    + _tags(item.get("department"), location),
                    external_id=str(item["id"]) if item.get("id") else None,
                )
            )
        return [j for j in jobs if j.title and j.url]


class PersonioProvider(ATSProvider):
    """Personio XML feed (``{company}.jobs.personio.de/xml``)."""

    provider_name = "personio"
    endpoint_tpl = "https://{company}.jobs.personio.de/xml"

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        url_tpl = self.config.get("url_tpl")
        if not url_tpl:
            raise ValueError(
                "personio requires a 'url_tpl' entry in the source config: the XML "
                "feed has no job URL (e.g. https://{company}.jobs.personio.de/job/{id})"
            )
        try:
            root = ElementTree.fromstring(page.html_content or "")
        except ElementTree.ParseError as exc:
            raise ValueError(f"personio: feed is not valid XML ({exc})") from exc

        jobs: list[RawJob] = []
        for position in root.findall("position"):
            position_id = _xml_text(position, "id")
            if not position_id:
                continue
            try:
                url = str(url_tpl).format(id=position_id, **self.config)
            except (KeyError, IndexError, ValueError) as exc:
                raise ValueError(
                    f"personio could not render url_tpl {str(url_tpl)!r}: {exc}"
                ) from exc

            extra_offices = [
                node.text.strip()
                for node in position.findall("additionalOffices/office")
                if node.text and node.text.strip()
            ]
            location = ", ".join(
                part for part in [_xml_text(position, "office"), *extra_offices] if part
            )
            description = (
                _strip_html(
                    " ".join(
                        node.text or ""
                        for node in position.findall(
                            "jobDescriptions/jobDescription/value"
                        )
                    )
                )[:2000]
                or None
            )
            jobs.append(
                RawJob(
                    title=_xml_text(position, "name") or "",
                    company=_xml_text(position, "subcompany")
                    or self.config.get("company")
                    or "",
                    url=url,
                    posted_date=coerce_date(_xml_text(position, "createdAt")),
                    description=description,
                    tags=_tags(
                        _xml_text(position, "department"),
                        _xml_text(position, "recruitingCategory"),
                        _xml_text(position, "employmentType"),
                        _xml_text(position, "seniority"),
                        location,
                    ),
                    external_id=position_id,
                )
            )

        jobs = [job for job in jobs if job.title and job.url]
        max_results = int(self.config.get("max_results") or 0)
        return jobs[:max_results] if max_results > 0 else jobs


class WorkdayProvider(ATSProvider):
    """Workday CXS job API — public JSON, reached with a POST."""

    provider_name = "workday"
    endpoint_tpl = "https://{host}/wday/cxs/{tenant}/{site}/jobs"
    job_tpl = "https://{host}/{locale}/{site}{external_path}"

    def _request_payload(self) -> dict:
        """The CXS search body (no facets, single page, capped by max_results)."""
        return {
            "appliedFacets": {},
            "limit": int(self.config.get("max_results") or 20),
            "offset": 0,
            "searchText": str(self.config.get("query") or ""),
        }

    async def fetch(self, url: str, *, auth: FetchAuth | None = None) -> ScrapedPage:
        """POST the CXS search payload (the pipeline only supplies the URL)."""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth and auth.headers:
            headers.update(auth.headers)
        assert_safe_url(url)
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.post(url, headers=headers, json=self._request_payload())
            resp.raise_for_status()
            if len(resp.content) > settings.scraper_max_response_bytes:
                raise ValueError(
                    "Response exceeds "
                    f"scraper_max_response_bytes ({settings.scraper_max_response_bytes})"
                )
            return ScrapedPage(
                html_content=resp.text,
                status_code=resp.status_code,
                final_url=url,
            )

    def _jobs_from_payload(self, data):
        jobs: list[RawJob] = []
        for item in data.get("jobPostings", []):
            external_path = item.get("externalPath") or ""
            bullets = [str(value) for value in (item.get("bulletFields") or []) if value]
            url = None
            if external_path:
                url = self.job_tpl.format(
                    host=self.config.get("host", ""),
                    locale=self.config.get("locale", "en-US"),
                    site=self.config.get("site", ""),
                    external_path=external_path,
                )
            jobs.append(
                RawJob(
                    title=item.get("title") or "",
                    company=self.config.get("company") or self.config.get("tenant") or "",
                    url=url,
                    posted_date=coerce_date(item.get("postedOn")),
                    tags=_tags(item.get("locationsText"), *bullets),
                    external_id=bullets[0] if bullets else None,
                )
            )
        return [j for j in jobs if j.title and j.url]


class JsonListProvider(DiscoveryProvider):
    """Config-driven provider for boards exposing a JSON array of jobs."""

    provider_name = "json_list"
    family = "json"
    requires_key = False

    def results_url(self) -> str:
        url = self.config.get("url") or self.config.get("url_tpl")
        if not url:
            raise ValueError(
                "json_list requires a 'url' or 'url_tpl' entry in the source config"
            )
        try:
            return str(url).format(**self.config)
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(
                f"json_list could not build the fetch URL from {str(url)!r}: {exc}"
            ) from exc

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        try:
            payload = json.loads(page.html_content or "")
        except json.JSONDecodeError as exc:
            raise ValueError(f"json_list: response is not valid JSON ({exc.msg})") from exc

        items = resolve_path(payload, self.config.get("items_path"))
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            raise ValueError(
                "json_list: 'items_path' must point to a JSON array of jobs "
                f"(got {type(items).__name__})"
            )

        company_fallback = str(self.config.get("company") or "").strip()
        jobs = [
            self._job_from_item(item, company_fallback, page.final_url)
            for item in items
            if isinstance(item, dict)
        ]
        jobs = [job for job in jobs if job.title and job.url]
        max_results = int(self.config.get("max_results") or 0)
        return jobs[:max_results] if max_results > 0 else jobs

    def _job_from_item(
        self, item: dict, company_fallback: str, base_url: str
    ) -> RawJob:
        def field(key: str) -> object:
            path = self.config.get(key)
            if not path:
                return None
            return resolve_path(item, path)

        url = as_optional_str(field("url_path"))
        location = as_optional_str(field("location_path"))
        tags = as_tag_list(field("tags_path"))
        if location:
            tags.append(location)

        raw_description = field("description_path")
        description = None
        if raw_description:
            description = _strip_html(str(raw_description))[:2000] or None

        return RawJob(
            title=str(field("title_path") or "").strip(),
            company=str(field("company_path") or "").strip() or company_fallback,
            url=urljoin(base_url, url) if url else None,
            posted_date=coerce_date(field("date_path")),
            description=description,
            tags=tags,
            external_id=as_optional_str(field("id_path")),
        )


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
    """Third-party search API covering LinkedIn Jobs / Indeed / Google Jobs."""

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
    """Bright Data Web Unlocker / SERP API: renders the target search page."""

    provider_name = "brightdata"
    key_header = "Authorization"

    def _target_url(self) -> str:
        """The URL Bright Data renders for us (config override, else the engine)."""
        override = self.config.get("url") or self.config.get("url_tpl")
        if override:
            try:
                return str(override).format(**self.config)
            except (KeyError, IndexError, ValueError) as exc:
                raise ValueError(
                    f"brightdata could not render the target URL {str(override)!r}: {exc}"
                ) from exc
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
            if len(resp.content) > settings.scraper_max_response_bytes:
                raise ValueError(
                    "Response exceeds "
                    f"scraper_max_response_bytes ({settings.scraper_max_response_bytes})"
                )
            return ScrapedPage(
                html_content=resp.text,
                status_code=resp.status_code,
                final_url=url,
            )

    def next_page_url(self, page: ScrapedPage) -> str | None:
        """Pagination is intentionally unsupported."""
        return None

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


_DISCOVERY_CONFIG_METADATA: dict[str, dict] = {
    "ashby": {
        "required": ("org",),
        "optional": ("company", "max_results"),
        "example": {"org": "acme", "company": "Acme"},
    },
    "greenhouse": {
        "required": ("board_token",),
        "optional": ("company", "max_results"),
        "example": {"board_token": "acme", "company": "Acme"},
    },
    "lever": {
        "required": ("company",),
        "optional": ("max_results",),
        "example": {"company": "acme"},
    },
    "workable": {
        "required": ("org",),
        "optional": ("company", "max_results"),
        "example": {"org": "acme", "company": "Acme"},
    },
    "smartrecruiters": {
        "required": ("company",),
        "optional": ("max_results",),
        "example": {"company": "acme", "max_results": 50},
    },
    "recruitee": {
        "required": ("company",),
        "optional": ("max_results",),
        "example": {"company": "acme"},
    },
    "personio": {
        "required": ("company", "url_tpl"),
        "optional": ("max_results",),
        "example": {
            "company": "acme",
            "url_tpl": "https://{company}.jobs.personio.de/job/{id}",
        },
    },
    "workday": {
        "required": ("host", "tenant", "site"),
        "optional": ("query", "locale", "company", "max_results"),
        "example": {
            "host": "acme.wd1.myworkdayjobs.com",
            "tenant": "acme",
            "site": "AcmeCareers",
            "company": "Acme",
        },
    },
    "json_list": {
        "required": (),
        "required_any": (("url", "url_tpl"),),
        "optional": (
            "items_path",
            "id_path",
            "title_path",
            "url_path",
            "company_path",
            "company",
            "location_path",
            "date_path",
            "tags_path",
            "description_path",
            "max_results",
        ),
        "example": {
            "url": "https://api.example/jobs",
            "items_path": "data.items",
            "title_path": "position",
            "url_path": "url",
            "company_path": "company",
            "date_path": "date",
        },
    },
    "google_cse": {
        "required": ("query", "cx"),
        "optional": ("count", "max_results", "detail_strategy", "selectors"),
        "example": {"query": "site:jobs.example python", "cx": "0123456789:abc"},
    },
    "bing": {
        "required": ("query",),
        "optional": ("count", "max_results", "detail_strategy", "selectors"),
        "example": {"query": "site:jobs.example python", "count": 20},
    },
    "brave": {
        "required": ("query",),
        "optional": ("count", "max_results", "detail_strategy", "selectors"),
        "example": {"query": "site:jobs.example python", "count": 20},
    },
    "serpapi": {
        "required": ("query",),
        "optional": (
            "engine",
            "location",
            "num",
            "max_results",
            "detail_strategy",
            "selectors",
        ),
        "example": {"engine": "google_jobs", "query": "python", "location": "Brazil"},
    },
    "brightdata": {
        "required": (),
        "optional": (
            "engine",
            "query",
            "location",
            "url",
            "url_tpl",
            "customer",
            "zone",
            "country",
            "locale",
            "result_selector",
            "max_results",
            "detail_strategy",
            "selectors",
        ),
        "example": {"engine": "linkedin", "query": "python", "location": "Brazil"},
    },
}


DISCOVERY_PROVIDERS: dict[str, type[DiscoveryProvider]] = {
    cls.provider_name: cls
    for cls in (
        AshbyProvider,
        GreenhouseProvider,
        LeverProvider,
        WorkableProvider,
        SmartRecruitersProvider,
        RecruiteeProvider,
        PersonioProvider,
        WorkdayProvider,
        JsonListProvider,
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
