"""Fetching helpers shared by all scrapers: user-agent rotation, robots.txt, rate limiting."""

import ipaddress
import json
import random
import re
import socket
import time
import unicodedata
import warnings
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from app.config import settings
from scrapers.types import FetchAuth, RawJob, ScrapedPage

USER_AGENTS = [ua.strip() for ua in settings.user_agents.split(",") if ua.strip()]

_ROBOTS_CACHE_TTL_SECONDS = 3600
# A failed fetch (timeout, 5xx, DNS blip) must be retried soon: caching it for
# an hour turns one network hiccup into four blocked sweeps.
_ROBOTS_FAILURE_TTL_SECONDS = 60


@dataclass(frozen=True)
class _RobotsCacheEntry:
    """A cached robots.txt outcome, including *why* there is no parser."""

    parser: RobotFileParser | None
    status_code: int | None
    fetched_at: float
    ttl: float
    error: str | None = None


@dataclass(frozen=True)
class RobotsDecision:
    """Outcome of a robots.txt check: a *rule* or a *failure*, never conflated.

    ``RobotFileParser.can_fetch`` answers ``False`` while the file has never
    been fetched. The old code cached that parser and reported it as a
    ``Disallow``, so a single DNS/TLS/timeout blip skipped a healthy source for
    an hour — and, through the skip backoff, for a whole day (Dev.pro, Oct
    2026). ``reason`` keeps the two cases apart so the worker can retry soon and
    the UI can say what actually happened.
    """

    allowed: bool
    reason: Literal["allowed", "disallowed", "unavailable"]
    robots_url: str
    status_code: int | None = None
    error: str | None = None


_robots_parser_cache: dict[str, _RobotsCacheEntry] = {}


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


def _robots_url(url: str) -> str:
    """``/robots.txt`` for the URL's origin (keeping its scheme)."""
    parsed = urlparse(url)
    scheme = parsed.scheme if parsed.scheme in ("http", "https") else "https"
    return f"{scheme}://{parsed.netloc}/robots.txt"


def _fetch_robots(robots_url: str) -> _RobotsCacheEntry:
    """Fetch and parse robots.txt once; never conflate a failure with a denial."""
    now = time.monotonic()
    status_code: int | None = None
    last_error: str | None = None
    # Identify honestly first; fall back to the browser-like UA used for page
    # fetches only when the site rejects or fails that request.
    for user_agent in (settings.scraper_bot_user_agent, random_user_agent()):
        try:
            resp = httpx.get(
                robots_url,
                timeout=5,
                follow_redirects=True,
                headers={"User-Agent": user_agent},
            )
        except Exception as exc:  # noqa: BLE001 - robots.txt is best-effort
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        status_code = resp.status_code
        if status_code == 200:
            parser = RobotFileParser()
            parser.parse(resp.text.splitlines())
            return _RobotsCacheEntry(parser, status_code, now, _ROBOTS_CACHE_TTL_SECONDS)
        if 400 <= status_code < 500:
            # RFC 9309: a 4xx (404/403/401) means the file is unavailable, which
            # means "no restrictions published" — *not* "block everything".
            return _RobotsCacheEntry(None, status_code, now, _ROBOTS_CACHE_TTL_SECONDS)
        last_error = f"HTTP {status_code}"

    return _RobotsCacheEntry(
        None, status_code, now, _ROBOTS_FAILURE_TTL_SECONDS, last_error
    )


def robots_decision(url: str) -> RobotsDecision:
    """Decide whether ``url`` may be fetched, and *why*.

    Outcomes (cached per host):

    - ``allowed`` / ``disallowed`` — from a successfully parsed robots.txt;
    - ``allowed`` — robots.txt returned 4xx (RFC 9309: nothing is disallowed);
    - ``unavailable`` (``allowed=False``) — the file could not be fetched at
      all (timeout, 5xx, DNS/TLS error). Callers must treat this as a
      *transient* failure: deny this attempt, retry soon, and never report it
      as a ``Disallow``. The negative result is cached for only 60 s.
    """
    host = domain_of(url)
    robots_url = _robots_url(url)
    now = time.monotonic()
    cached = _robots_parser_cache.get(host)
    if cached is None or now - cached.fetched_at >= cached.ttl:
        cached = _fetch_robots(robots_url)
        _robots_parser_cache[host] = cached

    if cached.parser is not None:
        allowed = cached.parser.can_fetch(settings.scraper_bot_user_agent, url)
        return RobotsDecision(
            allowed=allowed,
            reason="allowed" if allowed else "disallowed",
            robots_url=robots_url,
            status_code=cached.status_code,
        )
    if cached.status_code is not None and 400 <= cached.status_code < 500:
        return RobotsDecision(
            allowed=True,
            reason="allowed",
            robots_url=robots_url,
            status_code=cached.status_code,
        )
    return RobotsDecision(
        allowed=False,
        reason="unavailable",
        robots_url=robots_url,
        status_code=cached.status_code,
        error=cached.error,
    )


def is_allowed_by_robots(url: str) -> bool:
    """``True`` unless robots.txt explicitly disallows ``url`` (or is unreachable)."""
    return robots_decision(url).allowed



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


async def _read_capped(resp: httpx.Response, max_bytes: int | None = None) -> str:
    """Read a streamed response body, enforcing the size cap.

    ``max_bytes`` overrides ``settings.scraper_max_response_bytes`` for callers
    that know their payload is bigger: an ATS board dump carries every opening
    with its full description (see ``ATSProvider.max_response_bytes``).
    """
    limit = max_bytes or settings.scraper_max_response_bytes
    chunks: list[bytes] = []
    total = 0
    async for chunk in resp.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise ValueError(f"Response exceeds scraper_max_response_bytes ({limit})")
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
    max_bytes: int | None = None,
) -> ScrapedPage:
    """Fetch a URL and return a ``ScrapedPage`` with the response HTML.

    ``method``/``json_body`` cover keyed APIs that only answer to POST (Jooble,
    Adzuna's JSON endpoints). ``read_error_body`` attaches a redacted excerpt of
    the error payload to the raised ``httpx.HTTPStatusError`` so callers can show
    the provider's own message; the exception type and ``exc.response`` stay
    intact, so status-code handling in the scrape worker keeps working.
    ``max_bytes`` raises the size cap for payloads that are legitimately larger
    than a page (ATS board dumps).
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
                    html_content=await _read_capped(resp, max_bytes),
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
        seconds = float(value)
        # Lever (and a few other boards) date postings with epoch
        # *milliseconds*; no posting in this app's range is an 11-digit
        # seconds timestamp, so anything larger is scaled down.
        if abs(seconds) > 1e11:
            seconds /= 1000
        try:
            return datetime.fromtimestamp(seconds, tz=UTC).date()
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


def fold_text(value: str | None) -> str:
    """Case- and accent-insensitive text used for location matching.

    ``Sao Paulo``/``São Paulo`` and ``BRAZIL``/``brazil`` must be the same term;
    a board's payload is rarely consistent about either.
    """
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    return "".join(
        char for char in decomposed if not unicodedata.combining(char)
    ).casefold()


def location_terms(value: object) -> list[str]:
    """Normalize the ``locations`` config value (list or comma-separated string).

    An empty result means "no location gate": the source keeps every job.
    """
    return as_tag_list(value)


def _folded_term_pattern(term: str) -> re.Pattern[str]:
    """Word-aware, accent-insensitive matcher for one folded location term.

    Plain substring matching makes ``us`` match ``Australia`` and ``ba`` match
    ``Barcelona``; the lookarounds keep a term matching as a whole word (the
    folded text only contains ``a-z0-9`` after accents are stripped).
    """
    escaped = re.escape(term)
    prefix = r"(?<![a-z0-9])" if term[:1].isalnum() else ""
    suffix = r"(?![a-z0-9])" if term[-1:].isalnum() else ""
    return re.compile(prefix + escaped + suffix)


def location_allowed(location: str | None, terms: object) -> bool:
    """Whether a posting passes the configured location gate.

    The gate keeps a job when **any** configured term matches the detected
    location. Postings with no reported location are always kept: dropping them
    silently removes whole boards (``detail``-mode aggregators, RSS author
    locations) and looks like an empty scrape. A blank ``terms`` config also
    keeps everything.

    Matching is case- and accent-insensitive and term-bounded, so ``brazil``
    matches ``Remote - Brazil`` but ``us`` does not match ``Australia``.
    """
    normalized_terms = [fold_text(term).strip() for term in location_terms(terms)]
    normalized_terms = [term for term in normalized_terms if term]
    if not normalized_terms:
        return True
    folded = fold_text(location).strip()
    if not folded:
        return True
    return any(_folded_term_pattern(term).search(folded) for term in normalized_terms)


_RELATIVE_AGE_RE = re.compile(
    r"(?:(?:h[aá]|faz)\s*)?(\d+)\s*\+?\s*"
    r"(minute|hour|day|week|month|year|minuto|hora|dia|semana|m[eê]s(?:es)?|ano)s?"
    r"\s*(?:ago|atr[aá]s)?",
    re.IGNORECASE,
)
# Compact card labels such as AI Jobs' "1D"/"4D" (h=hour, d=day, w=week,
# m=month, y=year). Only accept the whole label so a title like "Level 3D"
# cannot become a date.
_RELATIVE_SHORT_RE = re.compile(r"^\s*(\d+)\s*([hdwmy])\s*$", re.IGNORECASE)
_RELATIVE_SHORT_DAYS = {"h": 0, "d": 1, "w": 7, "m": 30, "y": 365}
_RELATIVE_AGE_DAYS = {
    "minute": 0,
    "hour": 0,
    "day": 1,
    "week": 7,
    "month": 30,
    "year": 365,
    "minuto": 0,
    "hora": 0,
    "dia": 1,
    "semana": 7,
    "mês": 30,
    "mes": 30,
    "meses": 30,
    "ano": 365,
}
_RELATIVE_TODAY = {
    "just posted",
    "just now",
    "today",
    "today's",
    "hoje",
    "agora",
    "agora mesmo",
}
_RELATIVE_YESTERDAY = {"yesterday", "ontem"}


def relative_age(value: object) -> str | None:
    """Turn a human age ("3 days ago", "há 2 horas") into ``YYYY-MM-DD``.

    Search APIs (Google Jobs via SerpApi, indeed/linkedin engines) and many
    listing cards report the posting date as a relative label rather than a
    timestamp. Brazilian boards commonly use Portuguese labels, so those are
    parsed as well instead of leaving the row undated.
    """
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in _RELATIVE_TODAY:
        return datetime.now(UTC).date().isoformat()
    if text in _RELATIVE_YESTERDAY:
        return (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    short = _RELATIVE_SHORT_RE.match(text)
    if short:
        days = _RELATIVE_SHORT_DAYS[short.group(2).lower()] * int(short.group(1))
        return (datetime.now(UTC).date() - timedelta(days=days)).isoformat()
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


def compile_exclude_pattern(config: dict | None) -> re.Pattern[str] | None:
    """Compile the optional ``exclude_pattern`` (case-insensitive regex).

    Board cards sometimes carry labels that announce a stale row ("Vaga
    expirada") while still linking to a page; matching card/job text is a
    config-only way to drop them. A bad regex fails the run with an actionable
    message instead of silently keeping every row.
    """
    raw = (config or {}).get("exclude_pattern")
    if not raw:
        return None
    try:
        return re.compile(str(raw), re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"exclude_pattern is not a valid regex: {exc}") from exc


def filter_excluded_jobs(jobs: list[RawJob], config: dict | None) -> list[RawJob]:
    """Drop jobs whose title/company/description/tags match ``exclude_pattern``."""
    pattern = compile_exclude_pattern(config)
    if pattern is None:
        return jobs
    kept: list[RawJob] = []
    for job in jobs:
        haystack = " ".join(
            filter(
                None,
                [
                    job.title,
                    job.company,
                    job.description,
                    " ".join(job.tags),
                ],
            )
        )
        if not pattern.search(haystack):
            kept.append(job)
    return kept


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


def _json_ld_type_names(value: object) -> set[str]:
    """The lower-cased ``@type`` names in a JSON-LD node (string or list)."""
    if isinstance(value, str):
        return {value.lower()}
    if isinstance(value, list):
        return {str(item).lower() for item in value if item is not None}
    return set()


def _json_ld_job_postings(data: object):
    """Yield every ``JobPosting`` in a JSON-LD payload, including ``@graph``.

    Publishers wrap their nodes in ``@graph``, put several nodes in a list, and
    sometimes declare ``@type`` as a list. All three shapes are legal JSON-LD and
    appear on real boards, so recurse through graph/list containers instead of
    accepting only a top-level object whose ``@type`` is the literal string.
    """
    if isinstance(data, list):
        for item in data:
            yield from _json_ld_job_postings(item)
        return
    if not isinstance(data, dict):
        return
    if "jobposting" in _json_ld_type_names(data.get("@type")):
        yield data
    graph = data.get("@graph")
    if graph is not None and graph is not data:
        yield from _json_ld_job_postings(graph)


def _json_ld_country(value: object) -> str | None:
    """A country name from a JSON-LD ``addressCountry`` (string or object)."""
    if isinstance(value, dict):
        return as_optional_str(value.get("name") or value.get("@id"))
    return as_optional_str(value)


def _json_ld_location(item: dict) -> str | None:
    """The detected location of a schema.org ``JobPosting``.

    ``jobLocation`` is often a list of ``Place`` objects whose ``address`` is a
    ``PostalAddress`` — the shape every ``career_page`` source uses. A posting
    marked ``TELECOMMUTE`` without an address is reported as ``Remote``, and
    ``applicantLocationRequirements`` (the eligible-countries field) is the
    fallback for boards that only say who may apply.
    """
    parts: list[str] = []
    raw = item.get("jobLocation")
    for entry in raw if isinstance(raw, list) else [raw]:
        if isinstance(entry, str):
            value = entry.strip()
            if value:
                parts.append(value)
            continue
        if not isinstance(entry, dict):
            continue
        address = entry.get("address") if isinstance(entry.get("address"), dict) else entry
        pieces = [
            as_optional_str(address.get("addressLocality")),
            as_optional_str(address.get("addressRegion")),
            _json_ld_country(address.get("addressCountry")),
        ]
        text = ", ".join(piece for piece in pieces if piece)
        if text:
            parts.append(text)

    location_type = item.get("jobLocationType")
    types = {
        str(value).lower()
        for value in (location_type if isinstance(location_type, list) else [location_type])
        if value
    }
    if not parts and "telecommute" in types:
        parts.append("Remote")

    if not parts:
        requirements = item.get("applicantLocationRequirements")
        for requirement in requirements if isinstance(requirements, list) else [requirements]:
            name = (
                as_optional_str(requirement.get("name"))
                if isinstance(requirement, dict)
                else as_optional_str(requirement)
            )
            if name:
                parts.append(name)

    return ", ".join(dict.fromkeys(parts)) or None


def _json_ld_external_id(item: dict, company: str) -> str | None:
    """The posting's own id, or ``None`` when the JSON-LD only carries an org id.

    ``identifier`` is a ``PropertyValue`` and boards disagree about what it
    identifies. Radartec stamps the *employer's* id there
    (``{"@type": "PropertyValue", "name": "Radartec", "value": "1"}``), so every
    ad the board posts itself carries ``value: "1"``: taken as the posting id it
    makes 18 distinct jobs collide on ``uq_jobs_source_external_id``. An
    identifier that names the hiring organization describes the org, not the
    posting, so the row keeps no external id and is deduped by URL instead.
    """
    identifier = item.get("identifier")
    if isinstance(identifier, dict):
        name = as_optional_str(identifier.get("name"))
        if name and company and fold_text(name) == fold_text(company):
            return None
        identifier = identifier.get("value") or identifier.get("@id")
    elif identifier is not None:
        identifier = str(identifier)
    return as_optional_str(identifier)


def parse_json_ld_jobs(
    html_content: str, fallback_url: str | None = None
) -> list[RawJob]:
    """Extract schema.org ``JobPosting`` records from JSON-LD script blocks.

    Some boards omit ``url``/``@id`` from their ``JobPosting`` payload, so a
    detail page would otherwise lose the job during normalization. ``fallback_url``
    (typically the fetched page's final URL) supplies the job URL in that case.

    ``json.loads`` is called with ``strict=False`` because several boards embed
    literal newlines/tabs inside string values; strict JSON rejects the whole
    block and loses otherwise valid title/company/date data.
    """
    # The worker calls this on every page, including RSS feeds; parsing XML with
    # the HTML parser is intentional (and harmless), so don't log a warning for it.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(html_content, "lxml")
    jobs: list[RawJob] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or script.get_text() or "", strict=False)
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
        for item in _json_ld_job_postings(data):
            company_obj = item.get("hiringOrganization") or {}
            if isinstance(company_obj, list):
                company_obj = company_obj[0] if company_obj else {}
            company = company_obj.get("name") if isinstance(company_obj, dict) else ""
            identifier = _json_ld_external_id(item, company)
            jobs.append(
                RawJob(
                    title=item.get("title") or "",
                    company=company or "",
                    url=item.get("url") or item.get("@id") or fallback_url,
                    posted_date=_parse_date(item.get("datePosted")),
                    description=item.get("description"),
                    tags=as_tag_list(item.get("skills")),
                    location=_json_ld_location(item),
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
            location=location,
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
    title_exclude_selectors = _split_selectors(config.get("title_exclude_selector")) or []
    exclude_pattern = compile_exclude_pattern(config)
    jobs: list[RawJob] = []
    for item in items:
        # Check the whole card: stale labels often live outside title/company.
        if exclude_pattern and exclude_pattern.search(item.get_text(" ", strip=True)):
            continue
        title_node = item.select_one(config.get("title_selector") or "h2")
        url_node = item.select_one(config.get("url_selector") or "a")
        if url_node is None and item.name == "a":
            # Some boards make the row *itself* the link (`a.position-row` on
            # dev.pro). soupsieve has no `:scope`, so read the href off the row.
            url_node = item
        title = title_node.get_text(" ", strip=True) if title_node else None
        if title and title_node:
            # Status badges are sometimes rendered inside the title heading
            # ("Vaga X <span>Nova</span>"); remove their text before storing.
            for exclude_selector in title_exclude_selectors:
                for badge in title_node.select(exclude_selector):
                    badge_text = badge.get_text(" ", strip=True)
                    if badge_text and title.endswith(badge_text):
                        title = title[: -len(badge_text)].strip()
                    elif badge_text:
                        title = title.replace(badge_text, "", 1).strip()
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
                # Company-specific boards often have no company element on a
                # card; the configured name keeps those rows out of "Unknown".
                company=company or str(config.get("company") or ""),
                url=urljoin(page.final_url, str(url)),
                posted_date=date_from_node(date_node),
                description=description,
                location=location,
            )
        )
    return jobs
