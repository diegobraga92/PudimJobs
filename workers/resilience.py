"""Resilience primitives: a per-source circuit breaker and a per-domain rate limiter."""

import uuid
from urllib.parse import urlparse

import redis
from app.config import settings

# Sync client on purpose: Celery tasks run via asyncio.run(), one event loop per
# task, so an async client would leak connections across loops.
redis_client: redis.Redis = redis.Redis.from_url(
    settings.redis_url, decode_responses=True
)

CIRCUIT_KEY = "cb:{source_id}"
SKIP_BACKOFF_KEY = "skip:{source_id}"
SCRAPE_LOCK_KEY = "scrape:lock:{source_id}"

# Only the lock owner may release it: a task that overran its TTL must not
# delete a lock now owned by a newer run.
_RELEASE_LOCK_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)


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
    """Normalize a URL to its domain (host[:port]) for rate-limit scoping."""
    return urlparse(url).netloc


def rate_limit_wait(url: str, cooldown_seconds: int = 30) -> float:
    """Return the number of seconds the caller should wait before fetching."""
    ttl = redis_client.ttl(f"rate:{_domain_key(url)}")
    return max(0.0, float(ttl)) if ttl > 0 else 0.0


def rate_limit_mark(url: str, cooldown_seconds: int = 30) -> None:
    """Mark the domain as recently fetched (sets the cooldown TTL).

    ``0`` is a valid per-source setting (the API allows it) and disables the
    cooldown; Redis rejects ``EX 0``, so clear any previous mark instead.
    """
    key = f"rate:{_domain_key(url)}"
    if cooldown_seconds <= 0:
        redis_client.delete(key)
        return
    redis_client.set(key, "1", ex=cooldown_seconds)


def skip_backoff_active(source_id: str) -> bool:
    """True while a skipped source is in its retry backoff window."""
    return (
        redis_client.exists(SKIP_BACKOFF_KEY.format(source_id=source_id)) == 1
    )


def skip_backoff_mark(source_id: str, minutes: int | None = None) -> None:
    """Suppress re-enqueueing a skipped source for the backoff period.

    ``minutes`` overrides the configured 24 h backoff for *transient* skips
    (e.g. robots.txt unreachable), so a network blip does not freeze a source
    until the next day. A permanent ``Disallow`` keeps the long backoff.
    """
    ttl_minutes = settings.scrape_skip_backoff_minutes if minutes is None else minutes
    redis_client.set(
        SKIP_BACKOFF_KEY.format(source_id=source_id),
        "1",
        ex=max(1, ttl_minutes) * 60,
    )


def skip_backoff_clear(source_id: str) -> None:
    """Drop the backoff after a real attempt (success or failure)."""
    redis_client.delete(SKIP_BACKOFF_KEY.format(source_id=source_id))


def acquire_scrape_lock(source_id: str) -> str | None:
    """Try to claim the per-source scrape slot; return the lock token or None.

    Guards against duplicate concurrent runs (two sweeps, or a manual trigger
    racing the sweep). The TTL is longer than the hard task time limit so a
    worker killed mid-run cannot leave the source locked forever.
    """
    token = uuid.uuid4().hex
    acquired = redis_client.set(
        SCRAPE_LOCK_KEY.format(source_id=source_id),
        token,
        nx=True,
        ex=settings.scrape_task_time_limit_seconds + 60,
    )
    return token if acquired else None


def release_scrape_lock(source_id: str, token: str) -> None:
    """Release ``source_id``'s lock if (and only if) ``token`` still owns it."""
    redis_client.eval(
        _RELEASE_LOCK_LUA,
        1,
        SCRAPE_LOCK_KEY.format(source_id=source_id),
        token,
    )

