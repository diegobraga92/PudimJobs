"""Fetching helpers shared by all scrapers: user-agent rotation, robots.txt
compliance, and a per-domain rate limiter backed by Redis."""

import random
from urllib.parse import urlparse

import httpx
from app.config import settings

from scrapers.types import ScrapedPage

USER_AGENTS = [ua.strip() for ua in settings.user_agents.split(",") if ua.strip()]

_robots_allow_cache: dict[str, bool] = {}


def random_user_agent() -> str:
    """Pick a browser-like user agent from the configured pool."""
    return random.choice(USER_AGENTS) if USER_AGENTS else "PudimJobsBot/0.1"


def domain_of(url: str) -> str:
    return urlparse(url).netloc


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


async def fetch_html(url: str, *, timeout: float = 20.0) -> ScrapedPage:
    """Fetch a URL and return a ``ScrapedPage`` with the response HTML."""
    headers = {"User-Agent": random_user_agent(), "Accept-Language": "en-US,en;q=0.9"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return ScrapedPage(
            html_content=resp.text,
            status_code=resp.status_code,
            final_url=str(resp.url),
        )
