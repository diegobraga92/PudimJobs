"""Resilience primitives: a Redis-backed per-source circuit breaker and a
per-domain rate limiter. Shared by the scraping tasks.

Uses the **sync** ``redis`` client: Celery tasks run via ``asyncio.run()``
(one fresh event loop per task), so an async client would leak connections
across loops. Circuit-breaker/rate-limit operations are microsecond-scale and
safe to call from async code.
"""

import redis
from app.config import settings

redis_client: redis.Redis = redis.Redis.from_url(
    settings.redis_url, decode_responses=True
)

CIRCUIT_KEY = "cb:{source_id}"


class CircuitBreakerOpenError(Exception):
    """Raised when a source's circuit breaker is open (paused)."""


def circuit_breaker_is_open(source_id: str) -> bool:
    failures = redis_client.get(CIRCUIT_KEY.format(source_id=source_id))
    return failures is not None and int(failures) >= settings.circuit_breaker_threshold


def circuit_breaker_record_failure(source_id: str) -> None:
    key = CIRCUIT_KEY.format(source_id=source_id)
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, settings.circuit_breaker_ttl_seconds)
    pipe.execute()


def circuit_breaker_reset(source_id: str) -> None:
    redis_client.delete(CIRCUIT_KEY.format(source_id=source_id))


def _domain_key(url: str) -> str:
    stripped = url.split("//")[1] if "//" in url else url
    return stripped.split("/")[0]


def rate_limit_wait(url: str, cooldown_seconds: int = 30) -> float:
    """Return the number of seconds the caller should wait before fetching.

    A Redis key ``rate:{domain}`` with a TTL equal to the cooldown means the
    domain was fetched within the cooldown window.
    """
    ttl = redis_client.ttl(f"rate:{_domain_key(url)}")
    return max(0.0, float(ttl)) if ttl > 0 else 0.0


def rate_limit_mark(url: str, cooldown_seconds: int = 30) -> None:
    """Mark the domain as recently fetched (sets the cooldown TTL)."""
    redis_client.set(f"rate:{_domain_key(url)}", "1", ex=cooldown_seconds)

