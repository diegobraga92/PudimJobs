"""Fetching helpers shared by all scrapers: user-agent rotation, robots.txt
compliance, and a per-domain rate limiter backed by Redis."""

import ipaddress
import json
import random
import re
import socket
from datetime import date
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from scrapers.types import FetchAuth, RawJob, ScrapedPage

USER_AGENTS = [ua.strip() for ua in settings.user_agents.split(",") if ua.strip()]

_robots_allow_cache: dict[str, bool] = {}


def random_user_agent() -> str:
    """Pick a browser-like user agent from the configured pool."""
    return random.choice(USER_AGENTS) if USER_AGENTS else "PudimJobsBot/0.1"


def domain_of(url: str) -> str:
    return urlparse(url).netloc


def assert_safe_url(url: str) -> None:
    """SSRF guard: only public http(s) URLs may be fetched.

    Blocks non-http(s) schemes and hosts that resolve to private, loopback,
    link-local, multicast, reserved, or unspecified addresses. Set
    ``SCRAPER_ALLOW_PRIVATE_NETWORKS=true`` to allow internal targets (e.g. a
    LAN-hosted careers site); the default is safe for shared deployments.
    """
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
    """Check robots.txt for the domain (cached for 1h in-process).

    Phase 2 keeps an in-process cache; a Redis-backed cache is a future
    refinement. A failed robots.txt fetch defaults to *allowed*.
    """
    host = domain_of(url)
    if host in _robots_allow_cache:
        return _robots_allow_cache[host]

    robots_url = f"https://{host}/robots.txt"
    allowed = True
    try:
        resp = httpx.get(robots_url, timeout=5, follow_redirects=True)
        if resp.status_code == 200:
            user_agent = random_user_agent().split("/")[0]
            rules: list[str] = []
            current_agent: str | None = None
            for raw_line in resp.text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                key, _, value = line.partition(":")
                if key.strip().lower() == "user-agent":
                    current_agent = value.strip().lower()
                    continue
                if key.strip().lower() == "disallow" and current_agent in (user_agent.lower(), "*"):
                    rules.append(value.strip())
            path = urlparse(url).path or "/"
            for rule in rules:
                if rule and path.startswith(rule):
                    allowed = False
                    break
    except Exception:  # noqa: BLE001, S110 - robots.txt is best-effort only
        pass
    _robots_allow_cache[host] = allowed
    return allowed


def rate_limit_key(url: str, cooldown_seconds: int = 30) -> tuple[str, int]:
    """Return the Redis key and TTL for the per-domain rate limit."""
    return f"rate:{domain_of(url)}", cooldown_seconds


async def fetch_html(
    url: str,
    *,
    timeout: float = 20.0,
    auth: FetchAuth | None = None,
) -> ScrapedPage:
    """Fetch a URL and return a ``ScrapedPage`` with the response HTML.

    ``auth`` optionally provides extra headers (e.g. a bearer token) for
    authenticated sources. The target is validated against an SSRF blocklist
    first.
    """
    assert_safe_url(url)
    headers = {"User-Agent": random_user_agent(), "Accept-Language": "en-US,en;q=0.9"}
    if auth and auth.headers:
        headers.update(auth.headers)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return ScrapedPage(
            html_content=resp.text,
            status_code=resp.status_code,
            final_url=str(resp.url),
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


def parse_json_ld_jobs(html_content: str) -> list[RawJob]:
    """Extract schema.org ``JobPosting`` records from JSON-LD script blocks.

    Returns an empty list when the page has no ``JobPosting`` JSON-LD. This is
    the primary strategy for career pages and for job *detail* pages discovered
    by search providers.
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
            jobs.append(
                RawJob(
                    title=item.get("title") or "",
                    company=company or "",
                    url=item.get("url") or item.get("@id"),
                    posted_date=_parse_date(item.get("datePosted")),
                    description=item.get("description"),
                    tags=[tag for tag in (item.get("skills") or []) if isinstance(tag, str)],
                    external_id=item.get("identifier"),
                )
            )
    return jobs


def parse_job_detail(page: ScrapedPage, selectors: dict | None = None) -> list[RawJob]:
    """Best-effort single-listing parser for a job detail page (CSS selectors).

    ``selectors`` optionally overrides the default selector lists with
    comma-separated strings (``title_selectors``, ``company_selectors``,
    ``location_selectors``, ``description_selectors``, ``date_selectors``).
    Returns ``[]`` when the page does not look like a job listing.
    """
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
