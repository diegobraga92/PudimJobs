"""Discovery providers: search-engine and ATS-board job sources."""

import hashlib
import json
import logging
import re
import time
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.board_health import board_miss_active, board_miss_clear, board_miss_mark
from scrapers.ats_boards import AtsBoard, resolve_ats_board
from scrapers.base import AbstractScraper
from scrapers.types import FetchAuth, RawJob, ScrapedPage
from scrapers.utils import (
    as_flag,
    as_optional_str,
    as_tag_list,
    assert_safe_url,
    coerce_date,
    fetch_html,
    parse_html_list,
    parse_job_detail,
    parse_json_ld_jobs,
    redact_sensitive,
    relative_age,
    resolve_path,
)

#: Where ``json_list`` puts the API key: in the URL template, in the query
#: string, in a header, or as a path segment (Jooble).
_JSON_AUTH_LOCATIONS = frozenset({"url", "path", "query", "header"})
_JSON_METHODS = frozenset({"GET", "POST"})

#: A SerpApi ``extensions`` entry is a free-text chip ("Full-time", "$120K a
#: year", "5 days ago"). Only the age chips may become a posting date: parsing
#: "1 year contract" as "posted a year ago" would drop a fresh job from a
#: ``max_age_days`` filter.
_AGE_LABEL_RE = re.compile(
    r"\b(?:ago|atr[aá]s|h[aá]|faz|today|yesterday|hoje|ontem|"
    r"just\s+(?:posted|now))\b",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)


def _term_pattern(term: str) -> re.Pattern[str]:
    """Compile a case-insensitive, word-aware term matcher.

    ``\\b`` is not enough for terms such as ``c++`` (the trailing character is
    not a word character, so the boundary can never match) and it happily
    matches ``rust`` inside ``trust`` when the leading boundary is omitted.
    Explicit alphanumeric lookarounds cover both cases.
    """
    if not term.strip():
        return re.compile(r"(?!x)x")
    escaped = re.escape(term)
    prefix = r"(?<![A-Za-z0-9_])" if term[:1].isalnum() or term[:1] == "_" else ""
    suffix = r"(?![A-Za-z0-9_])" if term[-1:].isalnum() or term[-1:] == "_" else ""
    return re.compile(prefix + escaped + suffix, re.IGNORECASE)


def _fold_text(value: str) -> str:
    """Case- and accent-insensitive text used for location matching."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def _matches_any(patterns: list[re.Pattern[str]], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


#: Remote markers found in a Google Jobs result's title/location/extensions.
#: ``detected_extensions.work_from_home`` is the authoritative flag; these cover
#: results where Google omitted it.
_REMOTE_MARKER_RE = re.compile(
    r"\b(?:remote|remoto|remota|home[\s-]?office|work\s+from\s+home|anywhere)\b",
    re.IGNORECASE,
)


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
    """The display name of an ATS facet payload.

    SmartRecruiters facets carry ``{"label": "Full-time"}`` while Greenhouse
    departments use ``{"id": 1, "name": "Engineering"}``; both shapes occur.
    """
    if isinstance(container, dict):
        return as_optional_str(container.get("label") or container.get("name"))
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
    #: True when a provider pages through the request body, so an unchanged URL
    #: does not mean "no more pages" (see ``workers/tasks/scrape.py``).
    pagination_in_body: bool = False
    #: Fallback cap for the *detail* fetches of a run (``config['max_results']``
    #: wins). Providers whose per-job fetches cost money lower this.
    default_max_results: int = 20

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

    def parse_listing(self) -> bool:
        """True when jobs are parsed from the results page itself.

        Providers that can read the job fields straight off the search results
        page avoid one paid fetch per job (see ``docs/scraping.md``).
        """
        return False

    def robots_url(self, url: str) -> str | None:
        """The URL whose robots.txt governs a fetch of ``url``.

        Third-party renderers (Bright Data) fetch the *target* board on our
        behalf, so the target is what must be checked, not their API endpoint.
        A pure API call (SerpApi) is exempt and returns ``None``.
        """
        return url

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

    @classmethod
    def validate_config(cls, config: dict, *, has_api_key: bool | None = None) -> None:
        """Fail fast on config mistakes the contract cannot express (default: none).

        Called by ``validate_source_config`` when a source is created or updated,
        so providers that build URLs or bodies can prove they render.
        """
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
                "external_id": raw.external_id,
            }
            for raw in raw_jobs
            if raw.title and raw.title.strip() and raw.url
        ]


class ATSProvider(DiscoveryProvider):
    """One-stage provider: a board's public JSON endpoint yields jobs directly."""

    family = "ats"
    endpoint_tpl: str = ""
    #: Board dumps carry every opening with its full description, so the 2 MB
    #: cap meant for HTML pages drops the large ones (Ashby's ``openai`` board
    #: is ~13 MB, and an ATS sweep reads dozens of boards per run). Only these
    #: public board endpoints get the bigger budget.
    max_response_bytes: int = 16_000_000

    def results_url(self) -> str:
        try:
            return self.endpoint_tpl.format(**self.config)
        except KeyError as exc:
            raise ValueError(
                f"{self.provider_name} requires a '{exc.args[0]}' entry in source config"
            ) from exc

    async def fetch(self, url: str, *, auth: FetchAuth | None = None) -> ScrapedPage:
        return await fetch_html(url, auth=auth, max_bytes=self.max_response_bytes)

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
            address = item.get("address") if isinstance(item.get("address"), dict) else {}
            postal = (
                address.get("postalAddress")
                if isinstance(address.get("postalAddress"), dict)
                else {}
            )
            secondary = [
                as_optional_str(entry.get("location"))
                if isinstance(entry, dict)
                else as_optional_str(entry)
                for entry in item.get("secondaryLocations") or []
            ]
            tags = _tags(
                item.get("location"),
                *secondary,
                postal.get("addressCountry"),
                item.get("department"),
                item.get("team"),
                item.get("employmentType"),
                item.get("workplaceType"),
            )
            jobs.append(
                RawJob(
                    title=item.get("title") or "",
                    company=self.config.get("company") or self.config.get("org") or "",
                    url=item.get("jobUrl") or item.get("url"),
                    posted_date=coerce_date(item.get("publishedAt")),
                    description=_strip_html(description) or None,
                    tags=list(dict.fromkeys(tags)),
                    external_id=str(item["id"]) if item.get("id") else None,
                )
            )
        return [j for j in jobs if j.title and j.url]


class GreenhouseProvider(ATSProvider):
    provider_name = "greenhouse"
    endpoint_tpl = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"

    def results_url(self) -> str:
        """The board API, honouring the EU host used by European boards.

        ``?content=true`` is required: without it the payload carries the
        title and the metadata only, so ``content`` was always ``None`` and the
        keyword/location filter was blind (GitLab's board went from 1 to 14
        matches once the body was part of the text).
        """
        try:
            token = self.config["board_token"]
        except KeyError as exc:
            raise ValueError(
                "greenhouse requires a 'board_token' entry in source config"
            ) from exc
        host = self.config.get("api_host") or "boards-api.greenhouse.io"
        return f"https://{host}/v1/boards/{token}/jobs?content=true"

    async def fetch(self, url: str, *, auth: FetchAuth | None = None) -> ScrapedPage:
        """Fetch the board with each posting's body, falling back to the listing.

        A host that rejects ``content=true`` must not cost the sweep the whole
        board: the plain listing still yields every title, date and URL, just
        without descriptions. The fallback page keeps the *requested* URL as
        ``final_url`` so the sweep still recognises it as a board payload.
        """
        try:
            return await fetch_html(url, auth=auth, max_bytes=self.max_response_bytes)
        except (httpx.HTTPError, ValueError) as exc:
            parsed = urlparse(url)
            query = [
                (name, value)
                for name, value in parse_qsl(parsed.query, keep_blank_values=True)
                if name != "content"
            ]
            plain = urlunparse(parsed._replace(query=urlencode(query)))
            if plain == url:
                raise
            logger.warning(
                "greenhouse_content_fallback url=%s error=%s", url, exc
            )
            page = await fetch_html(plain, auth=auth, max_bytes=self.max_response_bytes)
            return ScrapedPage(
                html_content=page.html_content,
                status_code=page.status_code,
                final_url=url,
            )

    def _jobs_from_payload(self, data):
        jobs: list[RawJob] = []
        for item in data.get("jobs", []):
            location = _location_name(item.get("location"))
            description = _strip_html(item.get("content"))
            departments = [
                _label(entry) for entry in item.get("departments") or [] if _label(entry)
            ]
            jobs.append(
                RawJob(
                    title=item.get("title") or "",
                    company=self.config.get("company")
                    or self.config.get("board_token")
                    or "",
                    url=item.get("absolute_url"),
                    # `first_published` is the posting date; `updated_at` also
                    # moves when the company edits the ad, which made a fresh
                    # posting look old (and an old one look new).
                    posted_date=coerce_date(
                        item.get("first_published") or item.get("updated_at")
                    ),
                    description=description[:2000] if description else None,
                    tags=_tags(location, *departments),
                    external_id=str(item["id"]) if item.get("id") else None,
                    match_text=description or None,
                )
            )
        return [j for j in jobs if j.title and j.url]


class LeverProvider(ATSProvider):
    provider_name = "lever"
    endpoint_tpl = "https://api.lever.co/v0/postings/{company}?mode=json"

    def results_url(self) -> str:
        """The board API, optionally paged and pointed at Lever's EU host.

        A large Lever board can easily exceed the 2 MB response cap when it
        returns every description; ``limit=100`` keeps the listing inside it.
        """
        try:
            company = self.config["company"]
        except KeyError as exc:
            raise ValueError("lever requires a 'company' entry in source config") from exc
        host = self.config.get("api_host") or "api.lever.co"
        url = f"https://{host}/v0/postings/{company}?mode=json"
        try:
            limit = int(self.config.get("limit") or 0)
        except (TypeError, ValueError):
            limit = 0
        return f"{url}&limit={limit}" if limit > 0 else url

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
                    # Lever reports ``createdAt`` as epoch milliseconds.
                    posted_date=coerce_date(item.get("createdAt")),
                    description=description,
                    tags=_tags(
                        cats.get("commitment"),
                        cats.get("location"),
                        *as_tag_list(cats.get("allLocations")),
                        cats.get("team"),
                        item.get("workplaceType"),
                    ),
                    external_id=str(item["id"]) if item.get("id") else None,
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
                    posted_date=coerce_date(
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
    """Config-driven provider for plain or keyed JSON job APIs.

    One config drives the whole request: ``url``/``url_tpl`` render with any
    config key plus the reserved ``{api_key}``, ``{page}`` and ``{page_size}``;
    ``method: POST`` + ``body`` covers APIs that only answer to POST (Jooble);
    ``auth`` says where the key travels (``query``/``header``/``path``); and
    ``next_page_tpl``/``max_pages`` paginate. Body placeholders substitute as
    text, so quote them the way the vendor expects (``"page": "{page}"``). The
    API key comes from the source's stored credentials, never from the config, so
    ``GET /api/sources`` keeps returning ``config`` verbatim.
    """

    provider_name = "json_list"
    family = "json"
    requires_key = False
    #: Job fields come from the payload itself, so the cap only bounds parses.
    default_max_results = 50
    #: True when the provider's URL carries a ``{page}`` marker.
    paginated = False
    #: Vendor defaults merged *under* the user's config (see ``__init__``).
    defaults: dict = {}

    def __init__(self, config: dict | None = None, api_key: str | None = None):
        super().__init__(config, api_key)
        self._page = 1
        # An empty form field must not shadow a vendor default (that would blank
        # out the baked-in field mapping).
        merged = dict(self.defaults)
        merged.update(
            {key: value for key, value in self.config.items() if value not in (None, "")}
        )
        self.config = merged

    # --- request building ---------------------------------------------------

    def page_size(self) -> int:
        """Results per page (``{page_size}`` in the URL, or the vendor's knob)."""
        return max(1, int(self.config.get("page_size") or 20))

    def max_pages(self) -> int:
        return max(1, int(self.config.get("max_pages") or 1))

    def _render_values(self, page: int | None = None) -> dict:
        values: dict = dict(self.config)
        values["page"] = self._page if page is None else page
        values["page_size"] = self.page_size()
        values["api_key"] = self.api_key or ""
        return values

    def _render(self, template: object, values: dict) -> str:
        """Substitute config keys, the page number and the API key."""
        text = str(template)
        if "{api_key}" in text and not self.api_key:
            raise ValueError(
                "json_list: this source needs an API key — its config uses "
                "{api_key}; add one in the source's Authentication panel"
            )
        try:
            return text.format(**values)
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(f"json_list could not render {text!r}: {exc}") from exc

    def results_url(self, page: int | None = None) -> str:
        return self._with_query_key(
            self._render(self._url_template(), self._render_values(page))
        )

    @classmethod
    def validate_config(cls, config: dict, *, has_api_key: bool | None = None) -> None:
        """Fail fast on config mistakes the contract cannot express.

        Runs the same rendering a fetch would do, so a bad ``method``, a POST
        without a ``body``, an unknown ``auth.in`` or a URL placeholder with no
        matching config key is reported when the source is saved instead of on
        the next scheduled run.

        ``has_api_key=None`` means "unknown": the key lives in the source's
        credentials and is often added right after the source is created, so the
        structural checks run with a probe key. Pass ``False`` to also demand a
        real key.
        """
        probe = cls(config, api_key=None if has_api_key is False else "probe")
        url = probe.results_url()
        probe.request_spec(url)
        if has_api_key is False and (cls.requires_key or "{api_key}" in json.dumps(config)):
            raise ValueError(
                f"{cls.provider_name} needs an API key — add one in the source's "
                "Authentication panel"
            )

    def _url_template(self) -> str:
        url = self.config.get("url") or self.config.get("url_tpl")
        if not url:
            raise ValueError(
                "json_list requires a 'url' or 'url_tpl' entry in the source config"
            )
        return str(url)

    def _auth_spec(self) -> tuple[str, str]:
        """Where the API key travels: ``(query|header|path, parameter name)``.

        An absent ``auth`` means "the URL template decides" (``{api_key}``),
        which keeps plain keyed boards working with no extra config.
        """
        raw = self.config.get("auth")
        if raw is None:
            return "url", ""
        if isinstance(raw, str):
            where, name = raw.strip().lower(), "X-API-Key"
        elif isinstance(raw, dict):
            where = str(raw.get("in") or "header").strip().lower()
            name = str(raw.get("name") or "X-API-Key").strip()
        else:
            raise ValueError("json_list: 'auth' must be a string or an object")
        if where not in _JSON_AUTH_LOCATIONS:
            raise ValueError(
                "json_list: 'auth.in' must be one of "
                f"{', '.join(sorted(_JSON_AUTH_LOCATIONS))} (got {where!r})"
            )
        return where, name

    def _with_query_key(self, url: str) -> str:
        where, name = self._auth_spec()
        if where != "query" or not self.api_key:
            return url
        separator = "&" if urlparse(url).query else "?"
        return f"{url}{separator}{urlencode({name: self.api_key})}"

    def _key_headers(self) -> dict[str, str]:
        where, name = self._auth_spec()
        return {name: self.api_key} if where == "header" and self.api_key else {}

    def _static_headers(self) -> dict[str, str]:
        raw = self.config.get("headers")
        if not isinstance(raw, dict):
            return {}
        return {str(key): str(value) for key, value in raw.items() if value is not None}

    def request_spec(self, url: str) -> tuple[str, dict | None]:
        """The HTTP method and JSON body used to fetch ``url``."""
        method = str(self.config.get("method") or "GET").strip().upper()
        if method not in _JSON_METHODS:
            raise ValueError(
                f"json_list: unsupported method {method!r} "
                f"(use {' or '.join(sorted(_JSON_METHODS))})"
            )
        if method == "GET":
            return method, None
        body = self.config.get("body")
        if not isinstance(body, dict):
            raise ValueError(
                "json_list: 'method: POST' requires a 'body' object in the config"
            )
        return method, self._render_body(body, self._render_values())

    def _render_body(self, node: object, values: dict) -> object:
        """Render every string inside a JSON body template."""
        if isinstance(node, str):
            return self._render(node, values) if "{" in node else node
        if isinstance(node, dict):
            return {key: self._render_body(value, values) for key, value in node.items()}
        if isinstance(node, list):
            return [self._render_body(item, values) for item in node]
        return node

    async def fetch(self, url: str, *, auth: FetchAuth | None = None) -> ScrapedPage:
        method, body = self.request_spec(url)
        headers = dict((auth.headers or {}) if auth else {})
        headers.update(self._static_headers())
        headers.update(self._key_headers())
        page = await fetch_html(
            url,
            auth=FetchAuth(headers=headers or None, api_key=self.api_key),
            method=method,
            json_body=body,
            # Providers put the real reason ("invalid api key", "quota exceeded")
            # in the payload; the snippet is capped and redacted.
            read_error_body=True,
        )
        # Some vendors take the key in the URL *path* (Jooble) and `final_url` is
        # handed back to the UI and run records: never echo the key.
        return replace(page, final_url=redact_sensitive(page.final_url, self.api_key))

    def _paginates_in_url(self) -> bool:
        if self.paginated:
            return True
        raw = self.config.get("url") or self.config.get("url_tpl")
        return bool(raw) and "{page}" in str(raw)

    @property
    def pagination_in_body(self) -> bool:
        """True when the page number rides in the body, so the URL repeats.

        The scrape worker uses this to tell "same URL" (= this vendor pages via
        the body) from "same URL" (= there are no more pages).
        """
        body = self.config.get("body")
        return isinstance(body, dict) and "{page}" in json.dumps(body)

    def next_page_url(self, page: ScrapedPage) -> str | None:
        """The next results URL, or None (single-page sources stop here)."""
        if self._page >= self.max_pages():
            return None
        tpl = self.config.get("next_page_tpl")
        if not tpl and not self.pagination_in_body and not self._paginates_in_url():
            return None
        self._page += 1
        if tpl:
            return self._with_query_key(self._render(tpl, self._render_values()))
        # Vendors that page through the body keep the endpoint URL; the page
        # number reaches the request through `request_spec`.
        return self.results_url()


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

class AdzunaProvider(JsonListProvider):
    """Adzuna Search API — free key, jobs straight off the results payload.

    ``app_id`` lives in the config (it is not a secret); the ``app_key`` is the
    stored credential and travels in the query string as ``app_key``.
    """

    provider_name = "adzuna"
    family = "search_api"
    requires_key = True
    default_max_results = 5
    paginated = True
    #: Adzuna pages through the URL path (`/search/{page}`), one page per call.
    url_tpl = (
        "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
        "?app_id={app_id}&app_key={api_key}&results_per_page={page_size}"
        "&what={query}&where={location}"
    )
    defaults = {
        "country": "br",
        "query": "",
        "location": "",
        "page_size": 20,
        "items_path": "results",
        "id_path": "id",
        "title_path": "title",
        "url_path": "redirect_url",
        "company_path": "company.display_name",
        "location_path": "location.display_name",
        "date_path": "created",
        "description_path": "description",
    }

    def _url_template(self) -> str:
        """``url``/``url_tpl`` may still be overridden, e.g. for tests."""
        return str(self.config.get("url") or self.config.get("url_tpl") or self.url_tpl)


class JoobleProvider(JsonListProvider):
    """Jooble API — POST-only, key in the URL path, page number in the body."""

    provider_name = "jooble"
    family = "search_api"
    requires_key = True
    default_max_results = 5
    url_tpl = "https://jooble.org/api/{api_key}"
    defaults = {
        "method": "POST",
        "query": "",
        "location": "",
        # Jooble wants the page number as a string inside the JSON body; body
        # placeholders always render as strings, so `"{page}"` is exactly right.
        "body": {"keywords": "{query}", "location": "{location}", "page": "{page}"},
        "items_path": "jobs",
        "id_path": "id",
        "title_path": "title",
        "url_path": "link",
        "company_path": "company",
        "location_path": "location",
        "date_path": "updated",
        "description_path": "snippet",
    }

    def _url_template(self) -> str:
        return str(self.config.get("url") or self.config.get("url_tpl") or self.url_tpl)


class JSearchProvider(JsonListProvider):
    """JSearch (RapidAPI) — one keyed GET per page, jobs in ``data``."""

    provider_name = "jsearch"
    family = "search_api"
    requires_key = True
    default_max_results = 5
    paginated = True
    search_url = "https://jsearch.p.rapidapi.com/search"
    defaults = {
        "country": "br",
        "query": "",
        "page_size": 20,
        "items_path": "data",
        "id_path": "job_id",
        "title_path": "job_title",
        "url_path": "job_apply_link",
        "company_path": "employer_name",
        "location_path": "job_city",
        "date_path": "job_posted_at_datetime_utc",
        "description_path": "job_description",
    }

    def results_url(self, page: int | None = None) -> str:
        params: dict = {
            "query": str(self.config.get("query") or ""),
            "page": self._page if page is None else page,
            "num_pages": self.page_size(),
        }
        for key in ("country", "date_posted"):
            if self.config.get(key):
                params[key] = self.config[key]
        return f"{self.config.get('url') or self.search_url}?{urlencode(params)}"

    def _key_headers(self) -> dict[str, str]:
        """RapidAPI wants the key plus the host it was issued for."""
        headers = {"X-RapidAPI-Host": "jsearch.p.rapidapi.com"}
        if self.api_key:
            headers["X-RapidAPI-Key"] = self.api_key
        return headers


class TwoStageProvider(DiscoveryProvider):
    """Search-based provider: results page → links → fetch each detail page."""

    def discover_urls(self, page: ScrapedPage) -> list[str]:
        # In listing mode the results page carries the job fields itself, so
        # there is nothing (and no paid call) to fetch per job.
        if self.parse_listing():
            return []
        return self.result_links(page)

    def result_links(self, page: ScrapedPage) -> list[str]:
        raise NotImplementedError

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        """Parse a job *detail* page (JSON-LD first, CSS selectors fallback)."""
        strategy = self.config.get("detail_strategy", "json_ld")
        if strategy != "selectors":
            jobs = parse_json_ld_jobs(page.html_content, page.final_url)
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
    #: Every discovered job costs one extra API call (or credit), so a run keeps
    #: a short leash unless the source asks for more via ``max_results``.
    default_max_results = 5

    def __init__(self, config: dict | None = None, api_key: str | None = None):
        super().__init__(config, api_key)
        self._offset = 0
        self._query_index = 0
        # Set by `DiscoveryScraper` for ATS sweeps: a sweep has to read every
        # configured query, not only the pages of the first one.
        self.rotate_queries = False
        self._pages_used = 0

    def _queries(self) -> list[str]:
        """The configured query list, falling back to the single ``query`` key."""
        raw = self.config.get("queries")
        if isinstance(raw, (list, tuple)):
            queries = [str(query).strip() for query in raw if str(query).strip()]
            if queries:
                return queries
        query = str(self.config.get("query") or "").strip()
        return [query] if query else []

    def current_query(self) -> str:
        queries = self._queries()
        if not queries:
            return ""
        return queries[min(self._query_index, len(queries) - 1)]

    def _has_more_queries(self) -> bool:
        return self._query_index + 1 < len(self._queries())

    @property
    def query_count(self) -> int:
        return len(self._queries())

    @property
    def queries_after_current(self) -> int:
        """How many queries still follow the one being read."""
        return max(0, self.query_count - (self._query_index + 1))

    @property
    def pages_per_query(self) -> int:
        """Pages to read per query before moving on (source ``max_pages``)."""
        try:
            return max(1, int(self.config.get("max_pages", 1)))
        except (TypeError, ValueError):
            return 1


    @classmethod
    def validate_config(cls, config: dict, *, has_api_key: bool | None = None) -> None:
        """Require a key when the caller knows none is stored.

        ``has_api_key=None`` means "unknown": a source is usually created before
        its key is added, so creation must keep working.
        """
        super().validate_config(config, has_api_key=has_api_key)
        queries = config.get("queries")
        if queries is not None:
            if not isinstance(queries, (list, tuple)):
                raise ValueError("config['queries'] must be a list of query strings")
            if any(not isinstance(query, str) or not query.strip() for query in queries):
                raise ValueError("config['queries'] must contain only non-empty strings")
        if has_api_key is False:
            raise ValueError(
                f"{cls.provider_name} needs an API key — add one in the source's "
                "Authentication panel"
            )

    def next_page_url(self, page: ScrapedPage) -> str | None:
        """Continue the current query, then move on to the next one."""
        # A sweep reads one page per query by default: search APIs report
        # "more results available" on nearly every page, so without this the
        # first query would consume the entire board budget.
        if self.rotate_queries and self._pages_used + 1 >= self.pages_per_query:
            return self._next_query_url()
        next_offset = self._next_offset(page)
        if next_offset:
            self._offset = int(next_offset)
            self._pages_used += 1
            return self.build_results_url(int(next_offset))
        return self._next_query_url()

    def _next_query_url(self) -> str | None:
        """Advance to the next configured query, or ``None`` when exhausted."""
        if not self._has_more_queries():
            return None
        self._query_index += 1
        self._offset = 0
        self._pages_used = 0
        if hasattr(self, "_page"):
            self._page = 1
        return self.build_results_url()

    def parse_listing(self) -> bool:
        """``parse_listing: true`` (or ``parse_mode: results``) parses the page."""
        if as_flag(self.config.get("parse_listing")):
            return True
        mode = str(self.config.get("parse_mode") or "").strip().lower()
        return mode in {"listing", "list", "results"}

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        if self.key_header and self.api_key:
            headers = dict((auth.headers or {}) if auth else {})
            headers[self.key_header] = self.api_key
            return await fetch_html(
                url,
                auth=FetchAuth(headers=headers, api_key=self.api_key),
                # Vendors explain rejected queries/keys in the payload (Brave's
                # missing-header 422, for example); keep the snippet redacted.
                read_error_body=True,
            )
        return await fetch_html(url, auth=auth, read_error_body=True)

    def results_url(self) -> str:
        return self.build_results_url()


class GoogleCseProvider(SearchApiProvider):
    provider_name = "google_cse"

    def build_results_url(self, offset: int | None = None) -> str:
        params = {
            "key": self.api_key or "",
            "cx": self.config.get("cx", ""),
            "q": self.current_query(),
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
            "q": self.current_query(),
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
            "q": self.current_query(),
            "count": int(self.config.get("count") or 10),
        }
        # Brave's `offset` is a *page* number (0-9), not a result index.  Its
        # `next_offset` field also reports the following page, so passing that
        # value straight through used to jump two pages or overshoot the cap.
        if offset:
            params["offset"] = offset
        for key in ("country", "search_lang", "freshness", "safesearch"):
            if self.config.get(key):
                params[key] = self.config[key]
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
        query = data.get("query") if isinstance(data.get("query"), dict) else {}
        if not query.get("more_results_available"):
            return None
        next_page = int(getattr(self, "_offset", 0) or 0) + 1
        return next_page if next_page <= 9 else None


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
        # Google Jobs localises both the index and the returned board links from
        # these; without them a "remote" query is answered from the US locale.
        for key in ("gl", "hl"):
            if self.config.get(key):
                params[key] = self.config[key]
        if self.config.get("num"):
            params["num"] = self.config["num"]
        if offset:
            params["start"] = offset
        return "https://serpapi.com/search?" + urlencode(params)

    def robots_url(self, url: str) -> str | None:
        """SerpApi is an API: its own robots.txt does not govern our queries.

        SerpApi serves ``/search`` with ``Disallow: /search?``; checking that
        path would skip every scheduled run even though we are calling a paid
        API, not crawling a page. Board/detail URLs (``apply_options[].link``)
        are still real pages and keep their normal robots check.
        """
        host = (urlparse(url).hostname or "").lower()
        if host == "serpapi.com" or host.endswith(".serpapi.com"):
            return None
        return url

    def _results_mode(self) -> bool:
        return str(self.config.get("parse_mode") or "").strip().lower() == "results"

    def parse_listing(self) -> bool:
        """``parse_mode: results`` reads the jobs straight off the SERP payload."""
        return self._results_mode() or super().parse_listing()

    def _job_link(self, item: dict) -> str | None:
        """The most useful link for a result.

        SerpApi's ``link``/``job_google_link``/``share_link`` point at
        ``google.com/search?ibp=htl;jobs…`` and only work inside a browser
        session; ``apply_options[].link`` holds the real board/ATS URL, so it
        comes first (``link_source: google`` restores the old ordering).
        """
        apply_links = [
            link
            for option in (item.get("apply_options") or [])
            if isinstance(option, dict)
            for link in [as_optional_str(option.get("link"))]
            if link
        ]
        google_links = [
            as_optional_str(item.get(key))
            for key in ("link", "job_google_link", "share_link", "apply_link", "url")
        ]
        candidates = google_links + apply_links
        if str(self.config.get("link_source") or "").strip().lower() != "google":
            candidates = apply_links + google_links
        return next((link for link in candidates if link), None)

    def _via_terms(self) -> list[str]:
        """Configured board names for ``via_filter`` (empty means no filtering)."""
        raw = self.config.get("via_filter")
        if isinstance(raw, bool):
            return ["glassdoor"] if raw else []
        return [term.lower() for term in as_tag_list(raw)]

    def _matches_filters(self, item: dict) -> bool:
        """Apply the optional ``via_filter`` and ``remote_only`` result filters."""
        via_terms = self._via_terms()
        if via_terms:
            sources = [item.get("via")]
            for option in item.get("apply_options") or []:
                if isinstance(option, dict):
                    sources.extend((option.get("title"), option.get("link")))
            haystack = " ".join(str(value) for value in sources if value).lower()
            if not any(term in haystack for term in via_terms):
                return False

        if not as_flag(self.config.get("remote_only")):
            return True
        detected = item.get("detected_extensions")
        if isinstance(detected, dict) and as_flag(detected.get("work_from_home")):
            return True
        markers = [item.get("title"), item.get("location")]
        markers.extend(as_tag_list(item.get("extensions")))
        return any(
            _REMOTE_MARKER_RE.search(str(value)) for value in markers if value
        )

    def result_links(self, page: ScrapedPage) -> list[str]:
        data = json.loads(page.html_content)
        links: list[str] = []
        for item in data.get("jobs_results", []):
            if not isinstance(item, dict) or not self._matches_filters(item):
                continue
            link = self._job_link(item)
            if link:
                links.append(link)
        return links

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        if self._results_mode():
            return self._jobs_from_results(page)
        return super().parse(page)

    def _external_id(self, item: dict) -> str | None:
        """A database-safe external id from SerpApi's ``job_id``.

        Google Jobs returns a base64 payload of ~350 characters, which exceeds
        ``jobs.external_id VARCHAR(255)`` and aborted every insert. Hash only
        the over-long values so short/readable ids stay unchanged.
        """
        job_id = as_optional_str(item.get("job_id"))
        if not job_id:
            return None
        if len(job_id) <= 255:
            return job_id
        return "serpapi:" + hashlib.sha256(job_id.encode()).hexdigest()

    def _jobs_from_results(self, page: ScrapedPage) -> list[RawJob]:
        """Build ``RawJob``s from the results payload (no detail fetches)."""
        data = json.loads(page.html_content or "{}")
        jobs: list[RawJob] = []
        for item in data.get("jobs_results", []):
            if not isinstance(item, dict) or not self._matches_filters(item):
                continue
            location = as_optional_str(item.get("location"))
            tags = as_tag_list(item.get("extensions"))
            if location and location not in tags:
                tags.insert(0, location)
            detected = item.get("detected_extensions")
            detected = detected if isinstance(detected, dict) else {}
            description = self._description_from_result(item)
            jobs.append(
                RawJob(
                    title=str(item.get("title") or "").strip(),
                    company=str(item.get("company_name") or "").strip(),
                    url=self._job_link(item),
                    posted_date=self._posted_date(item, detected),
                    description=description,
                    tags=tags,
                    external_id=self._external_id(item),
                )
            )
        jobs = [job for job in jobs if job.title and job.url]
        max_results = int(self.config.get("max_results") or 0)
        return jobs[:max_results] if max_results > 0 else jobs

    def _posted_date(self, item: dict, detected: dict) -> date | None:
        """The posting age SerpApi reports as free text, not a timestamp.

        ``detected_extensions.posted_at`` exists on some engines (the LinkedIn
        one sends ``"3 days ago"``). Google Jobs carries the same information
        as an ``extensions`` chip, which is why every Google Jobs row used to
        be stored undated — invisible to the UI's date filter *and* to
        ``max_age_days``. Only chips that read like an age are parsed, so a
        salary or a contract length cannot become a posting date.
        """
        explicit = detected.get("posted_at")
        if explicit:
            parsed = coerce_date(relative_age(explicit) or explicit)
            if parsed:
                return parsed
        for label in item.get("extensions") or []:
            if not _AGE_LABEL_RE.search(str(label)):
                continue
            parsed = coerce_date(relative_age(label))
            if parsed:
                return parsed
        return None


    def _description_from_result(self, item: dict) -> str | None:
        description = as_optional_str(item.get("description"))
        if description:
            return description[:2000]
        highlights = item.get("job_highlights") or []
        parts: list[str] = []
        for group in highlights:
            if not isinstance(group, dict):
                continue
            parts.extend(str(value) for value in (group.get("items") or []) if value)
        return " ".join(parts)[:2000] or None

    def next_page_url(self, page: ScrapedPage) -> str | None:
        data = json.loads(page.html_content)
        next_url = (data.get("serpapi_pagination") or {}).get("next")
        if not next_url:
            return None
        if not self.api_key:
            return str(next_url)
        # SerpApi's `next` link omits the key, so following it verbatim returns
        # 401. Add it only when the vendor did not already include one.
        parsed = urlparse(str(next_url))
        query = parse_qsl(parsed.query, keep_blank_values=True)
        if not any(name == "api_key" for name, _ in query):
            query.append(("api_key", self.api_key))
        return urlunparse(parsed._replace(query=urlencode(query)))


class BrightDataProvider(SearchApiProvider):
    """Bright Data Web Unlocker / SERP API: renders the target search page.

    Two Bright Data endpoints exist and configs must match the zone they own:

    * ``endpoint: unlocker`` (default for LinkedIn/Indeed or a config ``url``)
      → ``POST https://api.brightdata.com/request`` with ``{"zone", "url"}``.
    * ``endpoint: serp`` → the legacy ``POST /serp/req?customer=&zone=``.

    ``endpoint`` may also be ``auto``/omitted (the default above) or an explicit
    ``https://`` URL for future endpoint changes.
    """

    provider_name = "brightdata"
    key_header = "Authorization"
    request_endpoint = "https://api.brightdata.com/request"
    serp_endpoint = "https://api.brightdata.com/serp/req"

    def __init__(self, config: dict | None = None, api_key: str | None = None):
        super().__init__(config, api_key)
        self._page = 1

    def endpoint_mode(self) -> str:
        """Which Bright Data API to call: ``"unlocker"`` or ``"serp"``."""
        mode = str(self.config.get("endpoint") or "").strip().lower()
        if mode in {"unlocker", "request", "web_unlocker"}:
            return "unlocker"
        if mode == "serp":
            return "serp"
        if self.config.get("url") or self.config.get("url_tpl"):
            return "unlocker"
        engine = str(self.config.get("engine") or "linkedin").strip().lower()
        # LinkedIn/Indeed are plain pages: the Web Unlocker renders them.
        return "unlocker" if engine in {"linkedin", "indeed"} else "serp"

    def _custom_endpoint(self) -> str | None:
        """An explicit ``endpoint`` URL (advanced; avoids waiting for a release)."""
        raw = str(self.config.get("endpoint") or "").strip()
        if raw.lower().startswith("https://"):
            return raw
        return None

    def build_results_url(self, offset: int | None = None) -> str:
        custom = self._custom_endpoint()
        if custom:
            return custom
        if self.endpoint_mode() == "serp":
            params = {
                "customer": self.config.get("customer", ""),
                "zone": self.config.get("zone", ""),
            }
            return self.serp_endpoint + "?" + urlencode(params)
        return self.request_endpoint

    def _is_provider_call(self, url: str) -> bool:
        """True when ``url`` is Bright Data's API, not a page to render."""
        if url == self.build_results_url():
            return True
        host = urlparse(url).netloc.lower()
        return host == "brightdata.com" or host.endswith(".brightdata.com")

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
        engine = str(self.config.get("engine") or "linkedin").strip().lower()
        query = self.config.get("query", "")
        location = self.config.get("location", "")
        page_tpl = self.config.get("page_tpl")
        page_params: dict[str, object] = {}
        if page_tpl and self._page > 1:
            try:
                page_params = {"start": str(page_tpl).format(page=self._page)}
            except (KeyError, IndexError, ValueError) as exc:
                raise ValueError(
                    f"brightdata could not render 'page_tpl' {str(page_tpl)!r}: {exc}"
                ) from exc
        if engine == "indeed":
            params = {"q": query, "l": location, **page_params}
            rendered = urlencode({k: v for k, v in params.items() if v})
            return f"https://br.indeed.com/jobs?{rendered}"
        params = {"keywords": query, "location": location, **page_params}
        rendered = urlencode({k: v for k, v in params.items() if v})
        return f"https://www.linkedin.com/jobs/search?{rendered}"

    def robots_url(self, url: str) -> str:
        """robots.txt is checked against the board, never Bright Data's API."""
        return self._target_url() if self._is_provider_call(url) else url

    def next_page_url(self, page: ScrapedPage) -> str | None:
        """Pagination for ``page_tpl`` configs (each page is a paid render).

        ``max_pages`` (read by the worker too) caps the number of renders.
        """
        page_tpl = self.config.get("page_tpl")
        target = self.config.get("url") or self.config.get("url_tpl")
        if not page_tpl or target:
            return None
        max_pages = int(self.config.get("max_pages") or 1)
        if self._page + 1 > max_pages:
            return None
        self._page += 1
        return self.build_results_url()

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        # The worker hands us either Bright Data's endpoint (results page, and
        # every paginated page) or a job *detail* URL discovered on it. Only the
        # former means "render the search page": re-rendering the SERP for a
        # detail URL is what burned ~20 paid calls and returned nothing.
        provider_call = self._is_provider_call(url)
        endpoint = url if provider_call else self.build_results_url()
        target = self._target_url() if provider_call else url
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: dict = {"url": target, "format": "raw"}
        # The Web Unlocker takes the zone in the body; /serp/req takes it (and
        # the customer id) in the query string, already part of the endpoint.
        if self.endpoint_mode() == "unlocker" and self.config.get("zone"):
            payload["zone"] = self.config["zone"]
            if self.config.get("customer"):
                payload["customer"] = self.config["customer"]
        if self.config.get("country"):
            payload["country"] = self.config["country"]
        if self.config.get("locale"):
            payload["locale"] = self.config["locale"]
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            if len(resp.content) > settings.scraper_max_response_bytes:
                raise ValueError(
                    "Response exceeds "
                    f"scraper_max_response_bytes ({settings.scraper_max_response_bytes})"
                )
            return ScrapedPage(
                html_content=resp.text,
                status_code=resp.status_code,
                final_url=target,
            )

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        if self.parse_listing():
            return parse_html_list(page, self.config)
        return super().parse(page)

    def result_links(self, page: ScrapedPage) -> list[str]:
        soup = BeautifulSoup(page.html_content, "lxml")
        selector = self.config.get("result_selector") or self._default_selector()
        links: list[str] = []
        for node in soup.select(selector):
            href = node.get("href") if hasattr(node, "get") else None
            if href:
                links.append(urljoin(page.final_url, str(href)))
        return links

    def _default_selector(self) -> str:
        if str(self.config.get("engine") or "linkedin").lower() == "indeed":
            return "h2.jobTitle a"
        return "a[href*='/jobs/view']"


#: Knobs shared by every search provider that can sweep ATS boards.
_SWEEP_OPTIONS = (
    "sweep_ats",
    "keywords",
    "exclude_keywords",
    "locations",
    "max_boards",
    "max_jobs",
    "allow_empty",
    # Budgeting knobs, so a multi-query sweep can be tuned from the API form
    # instead of only through a hand-edited config.
    "match_in",
    "board_rate_limit_seconds",
    "min_boards_per_query",
    "sweep_max_seconds",
    # Freshness gate; generic to every discovery source, exposed here so a
    # sweep can be bounded from the API form.
    "max_age_days",
)


_DISCOVERY_CONFIG_METADATA: dict[str, dict] = {
    "ashby": {
        "required": ("org",),
        "optional": ("company", "max_results"),
        "example": {"org": "acme", "company": "Acme"},
    },
    "greenhouse": {
        "required": ("board_token",),
        "optional": ("company", "api_host", "max_results"),
        "example": {"board_token": "acme", "company": "Acme"},
    },
    "lever": {
        "required": ("company",),
        "optional": ("api_host", "limit", "max_results"),
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
            "method",
            "body",
            "auth",
            "headers",
            "page_size",
            "next_page_tpl",
            "max_pages",
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
    "adzuna": {
        "required": ("app_id",),
        "optional": (
            "query",
            "country",
            "location",
            "page_size",
            "max_pages",
            "max_results",
        ),
        "example": {
            "app_id": "0123456789",
            "query": "python",
            "location": "sao paulo",
            "country": "br",
        },
    },
    "jooble": {
        "required": ("query",),
        "optional": ("location", "max_pages", "max_results"),
        "example": {"query": "python", "location": "Brazil"},
    },
    "jsearch": {
        "required": ("query",),
        "optional": (
            "country",
            "date_posted",
            "page_size",
            "max_pages",
            "max_results",
        ),
        "example": {"query": "python developer in Brazil", "date_posted": "week"},
    },
    "google_cse": {
        "required": ("cx",),
        "required_any": (("query", "queries"),),
        "optional": (
            "query",
            "queries",
            "count",
            "max_pages",
            "max_results",
            "detail_strategy",
            "selectors",
            *_SWEEP_OPTIONS,
        ),
        "example": {"query": "site:jobs.example python", "cx": "0123456789:abc"},
    },
    "bing": {
        "required": (),
        "required_any": (("query", "queries"),),
        "optional": (
            "query",
            "queries",
            "count",
            "max_pages",
            "max_results",
            "detail_strategy",
            "selectors",
            *_SWEEP_OPTIONS,
        ),
        "example": {"query": "site:jobs.example python", "count": 20},
    },
    "brave": {
        "required": (),
        "required_any": (("query", "queries"),),
        "optional": (
            "query",
            "queries",
            "count",
            "max_pages",
            "max_results",
            "country",
            "search_lang",
            "freshness",
            "safesearch",
            "detail_strategy",
            "selectors",
            *_SWEEP_OPTIONS,
        ),
        "example": {"query": "site:jobs.example python", "count": 20},
    },
    "serpapi": {
        "required": ("query",),
        "optional": (
            "engine",
            "location",
            "gl",
            "hl",
            "num",
            "parse_mode",
            "parse_listing",
            "link_source",
            "remote_only",
            "via_filter",
            "max_results",
            "max_pages",
            "allow_empty",
            "detail_strategy",
            "selectors",
            # A results-mode engine can fetch the jobs as well, so the age
            # gate applies here without a sweep.
            "max_age_days",
        ),
        "example": {
            "engine": "google_jobs",
            "query": "python remote",
            "gl": "us",
            "hl": "en",
            "parse_mode": "results",
            "remote_only": True,
        },
    },
    "brightdata": {
        "required": ("zone",),
        "required_any": (("engine", "url", "url_tpl"),),
        "optional": (
            "endpoint",
            "customer",
            "engine",
            "query",
            "location",
            "url",
            "url_tpl",
            "page_tpl",
            "country",
            "locale",
            "result_selector",
            "parse_listing",
            "item_selector",
            "title_selector",
            "url_selector",
            "company_selector",
            "location_selector",
            "date_selector",
            "description_selector",
            "max_results",
            "max_pages",
            "allow_empty",
            "detail_strategy",
            "selectors",
        ),
        "example": {
            "engine": "linkedin",
            "query": "python",
            "location": "Brazil",
            "zone": "web_unlocker1",
            "parse_listing": True,
            "item_selector": "li.jobs-search-results__list-item",
            "title_selector": "a.job-card-container__link",
            "url_selector": "a.job-card-container__link",
            "company_selector": ".artdeco-entity-lockup__subtitle",
            "location_selector": ".job-card-container__metadata-wrapper li",
        },
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
        AdzunaProvider,
        JoobleProvider,
        JSearchProvider,
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
    """Adapter exposing a ``DiscoveryProvider`` through the scraper contract.

    A search provider normally yields *job* links that are fetched one by one.
    With ``sweep_ats`` enabled it instead turns the search results into public
    ATS board APIs (Ashby, Lever, Greenhouse, SmartRecruiters) and reads those
    directly.  The worker's existing two-stage loop already fetches each
    discovered URL and calls :meth:`parse`, so no pipeline change is needed.

    The sweep filters locally because a board returns every job, not just the
    ones a search query would have found: ``keywords``/``exclude_keywords``
    match title, tags and description, and ``locations`` matches the title,
    location tags and description (case/accent-insensitive).
    """

    def __init__(
        self,
        provider_name: str,
        config: dict | None = None,
        api_key: str | None = None,
    ):
        self.provider = get_discovery_provider(provider_name, config, api_key)
        self._sweep = as_flag(self.provider.config.get("sweep_ats")) and isinstance(
            self.provider, TwoStageProvider
        )
        if self._sweep and isinstance(self.provider, SearchApiProvider):
            # A sweep exists to cover every query: spend `max_pages` per query
            # instead of letting the first one use the whole page budget.
            self.provider.rotate_queries = True
        # Start of the run, used by the optional `sweep_max_seconds` budget.
        self._started = time.monotonic()
        # Registered board API URL -> provider; the trailing slash is stripped
        # so a redirect (`/jobs` -> `/jobs/`) still finds its parser.
        self._board_providers: dict[str, DiscoveryProvider] = {}
        self._board_keys: set[tuple[str, str]] = set()
        # Every board the queries offered, including the ones `max_boards` or
        # the per-query reserve left unread: `offered` vs `boards` in the
        # summary line is what tells a budget-bound sweep from an index gap.
        self._offered_keys: set[tuple[str, str]] = set()
        self._jobs_emitted = 0
        # Run totals for the freshness gate: `stale` is what `max_age_days`
        # dropped, `undated` what it had to keep because the source reports no
        # date at all (Google Jobs' relative chips were the main case).
        self._stale_dropped = 0
        self._undated_kept = 0
        # `match_in: title` keeps keyword/exclusion matching on the title and
        # tags only: a board dump otherwise matches "Rust" mentioned once in an
        # unrelated job description.
        self._title_match = (
            str(self.provider.config.get("match_in") or "anywhere").strip().lower()
            in {"title", "titles", "title_and_tags"}
        )
        self._keyword_patterns = [
            _term_pattern(term)
            for term in as_tag_list(self.provider.config.get("keywords"))
            if term.strip()
        ]
        self._exclude_patterns = [
            _term_pattern(term)
            for term in as_tag_list(self.provider.config.get("exclude_keywords"))
            if term.strip()
        ]
        self._locations = [
            _fold_text(term)
            for term in as_tag_list(self.provider.config.get("locations"))
            if term.strip()
        ]

    @property
    def sweep_enabled(self) -> bool:
        return self._sweep

    @property
    def allow_empty(self) -> bool:
        """A sweep can legitimately find no matching jobs on a given day."""
        if "allow_empty" in self.provider.config:
            return as_flag(self.provider.config["allow_empty"])
        return self._sweep

    def first_fetch_url(self, source_url: str) -> str:
        return self.provider.results_url()

    @property
    def pagination_in_body(self) -> bool:
        """True when the provider pages through the request body (Jooble)."""
        return bool(getattr(self.provider, "pagination_in_body", False))

    @property
    def default_max_results(self) -> int:
        """The cap for detail fetches: boards in a sweep, paid calls otherwise."""
        if self._sweep:
            return self._max_boards()
        return int(getattr(self.provider, "default_max_results", 20))

    def _config_int(self, key: str, default: int) -> int:
        try:
            return int(self.provider.config.get(key, default))
        except (TypeError, ValueError):
            return default

    def page_limit(self, configured: int) -> int:
        """Total pages the worker may fetch in one run.

        ``max_pages`` bounds the pages read from a *single* query; a sweep has
        to read every configured query, so its budget is that limit times the
        number of queries. Without this the worker stopped after query #1 and
        the Lever/Greenhouse/SmartRecruiters queries never ran.
        """
        if not self._sweep or not isinstance(self.provider, SearchApiProvider):
            return configured
        return max(1, configured) * max(1, self.provider.query_count)

    def rate_limit_seconds_for(self, url: str, default: int) -> int:
        """Per-URL cooldown: board APIs get their own, shorter one.

        A sweep reads dozens of boards from a single API host
        (``api.ashbyhq.com``), each fetched exactly once per run. The search
        provider's cooldown (often 30 s) would make a multi-query sweep outlive
        its task time limit, so boards use ``board_rate_limit_seconds``.
        """
        if self._sweep and self._board_for(url) is not None:
            return max(0, self._config_int("board_rate_limit_seconds", 3))
        return default

    def _max_boards(self) -> int:
        return max(1, self._config_int("max_boards", 40))

    def _max_jobs(self) -> int:
        return max(0, self._config_int("max_jobs", 0))

    def _max_age_days(self) -> int:
        """Freshness window in days (``0`` = keep everything)."""
        return max(0, self._config_int("max_age_days", 0))

    def _drop_stale(self, jobs: list[RawJob]) -> list[RawJob]:
        """Drop postings older than ``max_age_days`` (``0`` disables the gate).

        A board dump repeats the company's whole backlog and a search API
        happily returns last year's posting, so freshness has to be enforced
        rather than hoped for. Two deliberate choices:

        * The gate runs on *every* discovery batch (board payloads and
          results-mode search payloads), because a source is not required to
          be a sweep to carry stale results.
        * Undated postings are kept. Several sources publish no date at all,
          and silently dropping them would look like an empty board; the run
          summary reports them as ``undated`` instead, so a source configured
          with ``max_age_days`` that reports no dates is visible in the log.
        """
        max_age = self._max_age_days()
        if max_age <= 0:
            return jobs
        cutoff = datetime.now(UTC).date() - timedelta(days=max_age)
        kept: list[RawJob] = []
        for job in jobs:
            if job.posted_date is None:
                self._undated_kept += 1
            elif job.posted_date < cutoff:
                self._stale_dropped += 1
                continue
            kept.append(job)
        return kept

    def _min_boards_per_query(self) -> int:
        return max(0, self._config_int("min_boards_per_query", 2))

    def _board_allowance(self) -> int:
        """Board slots the current search page may still use.

        Queries are visited in order, so the first query's boards could spend
        ``max_boards`` on their own and the later ATS queries would never run:
        every query not visited yet keeps ``min_boards_per_query`` slots.
        """
        budget = max(0, self._max_boards() - len(self._board_keys))
        if not isinstance(self.provider, SearchApiProvider):
            return budget
        reserve = self._min_boards_per_query() * self.provider.queries_after_current
        return max(0, budget - reserve)

    def _jobs_budget_spent(self) -> bool:
        max_jobs = self._max_jobs()
        return max_jobs > 0 and self._jobs_emitted >= max_jobs

    def _sweep_expired(self) -> bool:
        """True once ``sweep_max_seconds`` has elapsed (0 disables the cap)."""
        budget = self._config_int("sweep_max_seconds", 0)
        return budget > 0 and time.monotonic() - self._started >= budget

    def _register_board(self, board: AtsBoard) -> str:
        provider, url = self._board_target(board)
        self._board_providers[url.rstrip("/")] = provider
        return url

    def _board_target(self, board: AtsBoard) -> tuple[DiscoveryProvider, str]:
        """The provider for ``board`` and the URL it reads (not registered)."""
        provider = get_discovery_provider(board.ats, dict(board.config))
        return provider, provider.results_url()

    def _board_for(self, url: str) -> DiscoveryProvider | None:
        return self._board_providers.get(url.rstrip("/"))

    async def fetch(
        self, url: str, *, auth: FetchAuth | None = None
    ) -> ScrapedPage:
        provider = self._board_for(url)
        if provider is None:
            return await self.provider.fetch(url, auth=auth)
        # Board APIs are public and keyless: never forward the search provider's
        # credential to a third-party ATS.  One broken board must not sink the
        # sweep, so 404s, size caps and network errors become an empty page.
        try:
            page = await provider.fetch(url)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in {404, 410}:
                # The index keeps offering boards that no longer exist; park
                # them so the next sweeps spend their budget on live ones.
                board_miss_mark(url)
                logger.warning("ats_board_dead url=%s status=%s", url, status)
            else:
                logger.warning(
                    "ats_board_fetch_failed url=%s error=%s", url, exc
                )
            return ScrapedPage(html_content="", status_code=0, final_url=url)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("ats_board_fetch_failed url=%s error=%s", url, exc)
            return ScrapedPage(html_content="", status_code=0, final_url=url)
        board_miss_clear(url)
        return page

    def robots_url(self, url: str) -> str | None:
        # A public JSON board API is not a page crawl; the search provider still
        # decides whether its own results endpoint is governed by robots.txt.
        if self._sweep and self._board_for(url) is not None:
            return None
        return self.provider.robots_url(url)

    def check_credentials(self, has_api_key: bool) -> None:
        """Delegate to the provider (it knows whether a key is mandatory).

        The caller reports what it found in the source's credentials; an
        instance-built provider may already carry a key, and either is enough.
        """
        has_api_key = has_api_key or bool(self.provider.api_key)
        type(self.provider).validate_config(self.provider.config, has_api_key=has_api_key)

    def _filter_jobs(self, jobs: list[RawJob]) -> list[RawJob]:
        """Apply the local keyword/location filters and the ``max_jobs`` cap.

        ``match_in: title`` restricts keyword and exclusion matching to the
        title and tags. A board returns every opening the company has, so
        matching the description too keeps "Growth Lead" because the company
        blurb mentions Rust once. Locations still match the description: a
        board often carries the remote flag only in the body.
        """
        if not (self._keyword_patterns or self._exclude_patterns or self._locations):
            kept = list(jobs)
        else:
            kept = []
            for job in jobs:
                tags = " ".join(job.tags or [])
                headline = " ".join(part for part in (job.title, tags) if part)
                full_text = " ".join(
                    part
                    for part in (headline, job.match_text or job.description or "")
                    if part
                )
                haystack = headline if self._title_match else full_text
                if self._exclude_patterns and _matches_any(self._exclude_patterns, haystack):
                    continue
                if self._keyword_patterns and not _matches_any(
                    self._keyword_patterns, haystack
                ):
                    continue
                if self._locations:
                    folded = _fold_text(full_text)
                    if not any(location in folded for location in self._locations):
                        continue
                kept.append(job)

        max_jobs = self._max_jobs()
        if max_jobs > 0:
            remaining = max_jobs - self._jobs_emitted
            kept = kept[: max(0, remaining)]
        self._jobs_emitted += len(kept)
        return kept

    def parse(self, page: ScrapedPage) -> list[RawJob]:
        provider = self._board_for(page.final_url)
        if provider is None:
            # Results-mode search payloads (Google Jobs) are stored without any
            # local keyword filter, so they only pass the freshness gate.
            return self._drop_stale(self.provider.parse(page))
        if not page.html_content:
            return []
        try:
            jobs = provider.parse(page)
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            logger.warning(
                "ats_board_parse_failed url=%s error=%s", page.final_url, exc
            )
            return []
        if not self._sweep:
            return self._drop_stale(jobs)
        # Age first: a stale opening must not consume a `max_jobs` slot that a
        # fresh one would have used.
        kept = self._filter_jobs(self._drop_stale(jobs))
        # Openings vs kept separates "the board is dead/empty" from "the filter
        # dropped everything" — the two look identical in the job counts.
        logger.info(
            "ats_sweep_board_jobs url=%s openings=%s kept=%s",
            page.final_url,
            len(jobs),
            len(kept),
        )
        return kept

    async def discover_urls(self, page: ScrapedPage) -> list[str]:
        if not self._sweep or not isinstance(self.provider, TwoStageProvider):
            return self.provider.discover_urls(page)
        # The worker asks every fetched page for detail URLs, including the
        # board pages themselves.  Those payloads are a board JSON object or a
        # bare array, not search results, and must not be fed back to
        # `result_links` (a list has no `.get`).
        if self._board_for(page.final_url) is not None:
            return []
        # Nothing below can be stored once the run's budget is spent, and each
        # board fetch is a request: stop discovering instead of paying for it.
        if self._jobs_budget_spent() or self._sweep_expired():
            return []

        # `result_links` is used directly because a source may also set
        # `parse_listing`; that flag only affects the non-sweep path.
        allowance = self._board_allowance()
        query = (
            self.provider.current_query()
            if isinstance(self.provider, SearchApiProvider)
            else ""
        )
        urls: list[str] = []
        for link in self.provider.result_links(page):
            board = resolve_ats_board(link)
            if board is None:
                continue
            # Count before the allowance check: a board this page cannot afford
            # is still a board the query offered, and that gap is the number
            # `max_boards` has to grow by.
            self._offered_keys.add(board.key)
            if board.key in self._board_keys:
                continue
            try:
                provider, url = self._board_target(board)
            except ValueError as exc:
                logger.warning("ats_board_config_failed url=%s error=%s", link, exc)
                continue
            if board_miss_active(url):
                # A board that answered 404 last week is still a 404: skip it
                # without spending a slot or a request. It still counts as
                # offered, so `offered` keeps measuring the index, not us.
                logger.info("ats_sweep_board_skipped url=%s reason=dead", url)
                continue
            if len(urls) >= allowance:
                continue
            self._board_providers[url.rstrip("/")] = provider
            self._board_keys.add(board.key)
            # One line per board keeps the run's board manifest greppable:
            # the summary only carries totals, and a board that returns 404
            # would otherwise vanish without a trace.
            logger.info("ats_sweep_board query=%s ats=%s url=%s", query, board.ats, url)
            urls.append(url)
        return urls

    def next_page_url(self, page: ScrapedPage) -> str | None:
        # Search APIs are billed per request.  Once the board budget is spent no
        # later results page can add a board, so stop instead of paying for
        # pages whose links would only be discarded.
        if self._sweep:
            if len(self._board_keys) >= self._max_boards():
                return None
            if self._jobs_budget_spent():
                logger.info(
                    "ats_sweep_job_budget_spent boards=%s jobs=%s",
                    len(self._board_keys),
                    self._jobs_emitted,
                )
                return None
            if self._sweep_expired():
                logger.info(
                    "ats_sweep_time_budget_spent boards=%s jobs=%s",
                    len(self._board_keys),
                    self._jobs_emitted,
                )
                return None
        return self.provider.next_page_url(page)

    def normalize(self, raw_jobs: list[RawJob]) -> list[dict]:
        normalized = self.provider.normalize(raw_jobs)
        max_age = self._max_age_days()
        if max_age > 0:
            # One line per run: `undated` equal to `kept` means the source
            # reports no dates at all, so the window is doing nothing.
            logger.info(
                "discovery_age_filter max_age_days=%s stale=%s undated=%s kept=%s",
                max_age,
                self._stale_dropped,
                self._undated_kept,
                len(normalized),
            )
        if self._sweep:
            # One line per run so a silently shrinking sweep (dead boards, an
            # over-strict filter, a freshness window that eats everything) is
            # visible in the worker log.
            logger.info(
                "ats_sweep_summary boards=%s offered=%s jobs=%s stale=%s "
                "undated=%s queries=%s",
                len(self._board_providers),
                len(self._offered_keys),
                len(normalized),
                self._stale_dropped,
                self._undated_kept,
                self.provider.query_count
                if isinstance(self.provider, SearchApiProvider)
                else 1,
            )
        return normalized
