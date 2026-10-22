"""Negative cache for ATS boards that the search index still offers.

A search index keeps returning board URLs whose company moved ATS or renamed
its token, so every sweep re-pays for the same 404s. The audit of one run had
3 dead boards out of 50 read (~8% of the board budget), and the same URLs come
back on the next run because the ranking does not change. Remember the miss in
Redis for a week; when a company comes back the entry expires and the board is
read again.

Like ``skip_backoff``, this module has to stay importable from the backend
image, which ships ``backend/``, ``api/`` and ``scrapers/`` — hence the simple
sync client and no ``workers`` import.
"""

import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

# Sync client on purpose: Celery tasks run via asyncio.run(), one event loop per
# task, so an async client would leak connections across loops.
redis_client: redis.Redis = redis.Redis.from_url(
    settings.redis_url, decode_responses=True
)

#: One week: long enough to stop paying for a stale index entry, short enough
#: that a board coming back is picked up by the next sweep after that.
BOARD_MISS_TTL_SECONDS = 7 * 24 * 3600
BOARD_MISS_KEY = "ats_board_miss:{url}"


def board_miss_active(url: str) -> bool:
    """True while ``url`` is inside its known-dead window.

    A cache miss (Redis down, key absent) means "read the board": losing the
    cache costs requests, but it must never cost the sweep itself.
    """
    try:
        return redis_client.exists(BOARD_MISS_KEY.format(url=url)) == 1
    except redis.RedisError as exc:
        logger.warning("board_miss_lookup_failed url=%s error=%s", url, exc)
        return False


def board_miss_mark(url: str, *, ttl_seconds: int = BOARD_MISS_TTL_SECONDS) -> None:
    """Remember that ``url`` answered 404/410."""
    try:
        redis_client.set(
            BOARD_MISS_KEY.format(url=url), "1", ex=max(1, ttl_seconds)
        )
    except redis.RedisError as exc:
        logger.warning("board_miss_store_failed url=%s error=%s", url, exc)


def board_miss_clear(url: str) -> None:
    """Forget the miss (the board answered again)."""
    try:
        redis_client.delete(BOARD_MISS_KEY.format(url=url))
    except redis.RedisError as exc:
        logger.warning("board_miss_clear_failed url=%s error=%s", url, exc)

