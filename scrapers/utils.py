"""Fetching helpers shared by all scrapers: user-agent rotation, robots.txt, rate limiting."""

import ipaddress
import json
import random
import re
import socket
import time
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from scrapers.types import FetchAuth, RawJob, ScrapedPage

USER_AGENTS = [ua.strip() for ua in settings.user_agents.split(",") if ua.strip()]

_robots_parser_cache: dict[str, tuple[RobotFileParser, float]] = {}
_ROBOTS_CACHE_TTL_SECONDS = 3600

# Query params that may carry API keys/tokens; redacted from logs and errors.
# The parameter *name* must end with the sensitive word, so `keyword`/`monkey`
# are left alone while `app_key` (Adzuna) and `subscription-key` are caught.
_SENSITIVE_QUERY_PARAM_RE = re.compile(
    r"([?&][^=&\s#]*(?:api[_-]?key|key|token|secret|password|auth)=)[^&\s\"']*",
    re.IGNORECASE,
)

# Same idea for JSON payloads echoed back by providers, e.g.
# {"error": "invalid key", "api_key": "SECRET"}.
_SENSITIVE_JSON_FIELD_RE = re.compile(
    r'("(?:api_key|apikey|key|token|access_token|auth)"\s*:\s*)"[^"]*"',
    re.IGNORECASE,
)

# How much of a provider's error payload we keep in an exception message.
_ERROR_SNIPPET_CHARS = 300


def random_user_agent() -> str:
    """Pick a browser-like user agent from the configured pool."""
    return random.choice(USER_AGENTS) if USER_AGENTS else "PudimJobsBot/0.1"


def domain_of(url: str) -> str:
    return urlparse(url).netloc


def assert_safe_url(url: str) -> None:
    """SSRF guard: only public http(s) URLs may be fetched."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs are allowed (got {parsed.scheme!r})")
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no host")
    if settings.scraper_allow_private_networks:
        return
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"Could not resolve host {host!r}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(f"Blocked address {ip} for host {host!r}")


def is_allowed_by_robots(url: str) -> bool:
    """Check robots.txt for the domain (cached in-process for 1h)."""
    host = domain_of(url)
    now = time.monotonic()
    cached = _robots_parser_cache.get(host)
    if cached is None or now - cached[1] >= _ROBOTS_CACHE_TTL_SECONDS:
        parser = RobotFileParser()
        try:
            resp = httpx.get(
                f"https://{host}/robots.txt", timeout=5, follow_redirects=True
            )
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
        except Exception:  # noqa: BLE001 - robots.txt is best-effort only
            pass
        cached = (parser, now)
        _robots_parser_cache[host] = cached
    return cached[0].can_fetch(settings.scraper_bot_user_agent, url)


def rate_limit_key(url: str, cooldown_seconds: int = 30) -> tuple[str, int]:
    """Return the Redis key and TTL for the per-domain rate limit."""
    return f"rate:{domain_of(url)}", cooldown_seconds


def redact_sensitive(text: str, *secrets: str | None) -> str:
    """Redact API keys/tokens embedded in URLs or exception messages.

    ``secrets`` are the values we know about (the stored API key). Some vendors
    take the key in the URL *path* (Jooble), where no pattern can recognize it,
    so the caller passes the key along instead.
    """
    redacted = _SENSITIVE_QUERY_PARAM_RE.sub(r"\1REDACTED", text)
    redacted = _SENSITIVE_JSON_FIELD_RE.sub(r"\1\"REDACTED\"", redacted)
    for secret in secrets:
        # Short values would eat unrelated text (a 1-char key, "br", ...).
        if secret and len(secret) >= 4:
            redacted = redacted.replace(secret, "REDACTED")
    return redacted


async def _read_capped(resp: httpx.Response) -> str:
    """Read a streamed response body, enforcing the size cap."""
    max_bytes = settings.scraper_max_response_bytes
    chunks: list[bytes] = []
    total = 0
    async for chunk in resp.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(
                f"Response exceeds scraper_max_response_bytes ({max_bytes})"
            )
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


async def _error_snippet(resp: httpx.Response) -> str:
    """A capped, redacted one-line excerpt of an error response body.

    Diagnostics only: providers report the real reason ("invalid api key",
    "quota exceeded") in the payload, but a failure here must never mask the
    HTTP status the caller cares about.
    """
    try:
        body = await _read_capped(resp)
    except Exception:  # noqa: BLE001 - best effort diagnostics
        return ""
    return redact_sensitive(" ".join(body.split()))[:_ERROR_SNIPPET_CHARS]


async def fetch_html(
    url: str,
    *,
    timeout: float = 20.0,
    auth: FetchAuth | None = None,
    method: str = "GET",
    json_body: dict | None = None,
    read_error_body: bool = False,
) -> ScrapedPage:
    """Fetch a URL and return a ``ScrapedPage`` with the response HTML.

    ``method``/``json_body`` cover keyed APIs that only answer to POST (Jooble,
    Adzuna's JSON endpoints). ``read_error_body`` attaches a redacted excerpt of
    the error payload to the raised ``httpx.HTTPStatusError`` so callers can show
    the provider's own message; the exception type and ``exc.response`` stay
    intact, so status-code handling in the scrape worker keeps working.
    """
    headers = {"User-Agent": random_user_agent(), "Accept-Language": "en-US,en;q=0.9"}
    if auth and auth.headers:
        headers.update(auth.headers)
    verb = method.upper()

    current = url
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for _ in range(settings.scraper_max_redirects + 1):
            assert_safe_url(current)
            async with client.stream(
                verb, current, headers=headers, json=json_body
            ) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    current = urljoin(str(resp.url), resp.headers["location"])
                    continue
                if not read_error_body or not resp.is_error:
                    resp.raise_for_status()
                else:
                    api_key = auth.api_key if auth else None
                    snippet = await _error_snippet(resp)
                    detail = f": {snippet}" if snippet else ""
                    raise httpx.HTTPStatusError(
                        redact_sensitive(
                            f"HTTP {resp.status_code} from {resp.url}{detail}", api_key
                        ),
                        request=resp.request,
                        response=resp,
                    )
                return ScrapedPage(
                    html_content=await _read_capped(resp),
                    status_code=resp.status_code,
                    final_url=str(resp.url),
                )
        raise ValueError(
            f"Too many redirects (>{settings.scraper_max_redirects}) fetching {url}"
        )


# --- Shared parsing helpers ---------------------------------------------------


_TITLE_SELECTORS = ["h1[class*='job']", "h2[class*='job']", "h1", "h2", "[data-job-title]"]
_COMPANY_SELECTORS = ["[data-company]", ".company", ".employer", "meta[name='company']"]
_LOCATION_SELECTORS = ["[data-location]", ".location", ".job-location"]
_DESCRIPTION_SELECTORS = [
    "[data-job-description]",
    ".description",
    ".job-description",
    "#job-description",
]
_DATE_SELECTORS = ["[data-posted-date]", "time[datetime]", ".date", ".posted-date"]


def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    """Return the first non-empty text matched by ``selectors`` (or ``None``)."""
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


def _split_selectors(value: object) -> list[str] | None:
    """Normalize a ``str`` (comma-separated) or ``list`` of CSS selectors."""
    if value is None:
        return None
    if isinstance(value, list):
        return [str(s) for s in value if str(s).strip()]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return None


def resolve_path(data: object, path: object, *, default: object = None) -> object:
    """Resolve a dotted/indexed path inside a JSON payload (``a.b[0].c``)."""
    if not path:
        return data
    if not isinstance(path, str):
        return default
    current: object = data
    tokens = path.replace("[", ".").replace("]", "").split(".")
    for token in (part for part in tokens if part):
        if isinstance(current, dict):
            if token not in current:
                return default
            current = current[token]
        elif isinstance(current, list):
            try:
                index = int(token)
            except ValueError:
                return default
            if not -len(current) <= index < len(current):
                return default
            current = current[index]
        else:
            return default
    return current


def coerce_date(value: object) -> date | None:
    """Best-effort ``date`` from a JSON payload value."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC).date()
        except (OverflowError, OSError, ValueError):
            return None
    return _parse_date(str(value))


def as_tag_list(value: object) -> list[str]:
    """Normalize a payload value into tags (list, or comma-separated string)."""
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def as_optional_str(value: object) -> str | None:
    """A trimmed string from a payload value, or ``None`` when empty."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


_RELATIVE_AGE_RE = re.compile(r"(\d+)\s*\+?\s*(minute|hour|day|week|month)s?\s*ago", re.IGNORECASE)
_RELATIVE_AGE_DAYS = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30}


def relative_age(value: object) -> str | None:
    """Turn a human age ("3 days ago", "Just posted") into ``YYYY-MM-DD``.

    Search APIs (Google Jobs via SerpApi, indeed/linkedin engines) and many
    listing cards report the posting date as a relative label rather than a
    timestamp.
    """
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"just posted", "just now", "today", "today's"}:
        return datetime.now(UTC).date().isoformat()
    match = _RELATIVE_AGE_RE.search(text)
    if not match:
        return None
    days = _RELATIVE_AGE_DAYS[match.group(2).lower()] * int(match.group(1))
    return (datetime.now(UTC).date() - timedelta(days=days)).isoformat()


def as_flag(value: object) -> bool:
    """Interpret a config flag that may arrive as a bool or a JSON string."""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def date_from_node(node: object) -> date | None:
    """A date from a ``<time datetime=...>`` node, falling back to its text.

    The text may be absolute (``2026-08-01``) or a relative label
    (``"3 days ago"``), which is how most listings render it.
    """
    if node is None or not hasattr(node, "get_text"):
        return None
    raw = None
    if hasattr(node, "has_attr") and node.has_attr("datetime"):
        raw = node.get("datetime")
    text = node.get_text(" ", strip=True)
    return coerce_date(raw) or coerce_date(text) or coerce_date(relative_age(text))


def parse_json_ld_jobs(
    html_content: str, fallback_url: str | None = None
) -> list[RawJob]:
    """Extract schema.org ``JobPosting`` records from JSON-LD script blocks.

    Some boards omit ``url``/``@id`` from their ``JobPosting`` payload, so a
    detail page would otherwise lose the job during normalization. ``fallback_url``
    (typically the fetched page's final URL) supplies the job URL in that case.
    """
    soup = BeautifulSoup(html_content, "lxml")
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
            company_obj = item.get("hiringOrganization") or {}
            company = company_obj.get("name") if isinstance(company_obj, dict) else ""
            identifier = item.get("identifier")
            if isinstance(identifier, dict):
                identifier = identifier.get("value") or identifier.get("@id")
            elif identifier is not None:
                identifier = str(identifier)
            jobs.append(
                RawJob(
                    title=item.get("title") or "",
                    company=company or "",
                    url=item.get("url") or item.get("@id") or fallback_url,
                    posted_date=_parse_date(item.get("datePosted")),
                    description=item.get("description"),
                    tags=as_tag_list(item.get("skills")),
                    external_id=identifier,
                )
            )
    return jobs


def parse_job_detail(page: ScrapedPage, selectors: dict | None = None) -> list[RawJob]:
    """Best-effort single-listing parser for a job detail page (CSS selectors)."""
    selectors = selectors or {}
    title_sel = _split_selectors(selectors.get("title_selectors")) or _TITLE_SELECTORS
    company_sel = _split_selectors(selectors.get("company_selectors")) or _COMPANY_SELECTORS
    location_sel = _split_selectors(selectors.get("location_selectors")) or _LOCATION_SELECTORS
    description_sel = (
        _split_selectors(selectors.get("description_selectors")) or _DESCRIPTION_SELECTORS
    )
    date_sel = _split_selectors(selectors.get("date_selectors")) or _DATE_SELECTORS

    soup = BeautifulSoup(page.html_content, "lxml")
    title = _first_text(soup, title_sel)
    company = _first_text(soup, company_sel)
    if company is None and soup.find("meta", attrs={"name": "company"}):
        company = soup.find("meta", attrs={"name": "company"}).get("content")
    if not title or not company:
        return []
    description = _first_text(soup, description_sel)
    location = _first_text(soup, location_sel)
    if location:
        description = (
            f"{description} • Location: {location}" if description else f"Location: {location}"
        )
    return [
        RawJob(
            title=title,
            company=company,
            url=page.final_url,
            posted_date=_parse_date(_first_text(soup, date_sel)),
            description=description,
        )
    ]


def parse_html_list(page: ScrapedPage, config: dict | None = None) -> list[RawJob]:
    """Parse a *listing* page into one job per row (CSS-selector driven).

    Shared by the ``generic_html_list`` aggregator adapter and by search
    providers that parse the results page itself instead of fetching every
    detail page (``parse_listing``). Recognized keys: ``item_selector``,
    ``title_selector``, ``url_selector``, ``company_selector``,
    ``location_selector``, ``date_selector`` and the optional
    ``description_selector`` (a card snippet; location is appended to it). Every
    selector is evaluated *inside* the row; a row that is itself an ``<a>``
    contributes its own ``href``.
    """
    config = config or {}
    soup = BeautifulSoup(page.html_content, "lxml")
    items = soup.select(config.get("item_selector") or "article")
    date_selector = config.get("date_selector")
    description_selector = config.get("description_selector")
    jobs: list[RawJob] = []
    for item in items:
        title_node = item.select_one(config.get("title_selector") or "h2")
        url_node = item.select_one(config.get("url_selector") or "a")
        if url_node is None and item.name == "a":
            # Some boards make the row *itself* the link (`a.position-row` on
            # dev.pro). soupsieve has no `:scope`, so read the href off the row.
            url_node = item
        title = title_node.get_text(" ", strip=True) if title_node else None
        url = url_node.get("href") if url_node else None
        if not title or not url:
            continue
        company_node = item.select_one(config.get("company_selector") or ".company")
        location_node = item.select_one(config.get("location_selector") or ".location")
        company = company_node.get_text(" ", strip=True) if company_node else None
        location = location_node.get_text(" ", strip=True) if location_node else None

        description = None
        if description_selector:
            snippet_node = item.select_one(str(description_selector))
            description = snippet_node.get_text(" ", strip=True) if snippet_node else None
        if location:
            description = (
                f"{description} • Location: {location}" if description else f"Location: {location}"
            )

        date_node = item.select_one(date_selector) if date_selector else None
        jobs.append(
            RawJob(
                title=title,
                company=company or "",
                url=urljoin(page.final_url, str(url)),
                posted_date=date_from_node(date_node),
                description=description,
            )
        )
    return jobs
