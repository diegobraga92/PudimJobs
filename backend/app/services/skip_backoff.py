"""Per-source skip backoff state shared by the API and the worker.

The scraping engine parks a skipped source (robots.txt, missing API key, ...)
for a while so sweeps do not re-enqueue it every few minutes. The state lives in
Redis; the API clears it when a user explicitly asks to scrape a source now.

This module must stay importable from the backend image, which ships only
``backend/``, ``api/`` and ``scrapers/``. Importing the helpers from ``workers``
crashed the API at startup. The worker has ``/app/backend`` on its
``PYTHONPATH``, so ``workers.resilience`` re-exports these functions.
"""

import redis

from app.config import settings

# Sync client on purpose: Celery tasks run via asyncio.run(), one event loop per
# task, so an async client would leak connections across loops.
redis_client: redis.Redis = redis.Redis.from_url(
    settings.redis_url, decode_responses=True
)

SKIP_BACKOFF_KEY = "skip:{source_id}"


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
