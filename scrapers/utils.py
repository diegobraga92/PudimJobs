"""Fetching helpers shared by all scrapers: user-agent rotation, robots.txt
compliance, and a per-domain rate limiter backed by Redis."""

import ipaddress
import random
import socket
from urllib.parse import urlparse

import httpx
from app.config import settings

from scrapers.types import FetchAuth, ScrapedPage

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


def _cookies_dict(raw: str) -> dict[str, str]:
    """Parse a ``Cookie`` header string like ``"session=abc; csrf=xyz"``."""
    cookies: dict[str, str] = {}
    for part in raw.split(";"):
        if "=" in part:
            key, _, value = part.strip().partition("=")
            if key:
                cookies[key] = value
    return cookies


async def fetch_html(
    url: str,
    *,
    timeout: float = 20.0,
    auth: FetchAuth | None = None,
) -> ScrapedPage:
    """Fetch a URL and return a ``ScrapedPage`` with the response HTML.

    ``auth`` optionally provides cookies/headers for login-required sources.
    The target is validated against an SSRF blocklist first.
    """
    assert_safe_url(url)
    headers = {"User-Agent": random_user_agent(), "Accept-Language": "en-US,en;q=0.9"}
    cookies: dict[str, str] | None = None
    if auth:
        if auth.cookies:
            cookies = _cookies_dict(auth.cookies)
        if auth.headers:
            headers.update(auth.headers)
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, cookies=cookies
    ) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return ScrapedPage(
            html_content=resp.text,
            status_code=resp.status_code,
            final_url=str(resp.url),
        )
