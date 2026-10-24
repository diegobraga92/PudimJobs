"""Read-recency memory for ATS boards, so a sweep rotates its board budget.

A sweep offers far more boards than ``max_boards`` affords (~170 offered vs 50
read in the audited run).  Whichever boards lose that race lose it *every* run:
the query list and the index ranking change little from day to day, so a board
that does not fit today does not fit tomorrow either, and its postings are
missed for as long as they stay open.

Remember when each board was last read, and the sweep can prefer the ones it
has not seen for a while.  Coverage then accumulates across runs: with ~170
offered boards and 50 read per run, every board is read about once every four
runs, and a posting only has to be live at one of those reads to be stored
(``_store_jobs`` dedupes on URL/external id, so re-reading is cheap).

Like ``board_health``, this module has to stay importable from the backend
image, which ships ``backend/``, ``api/`` and ``scrapers/`` — hence the simple
sync client and no ``workers`` import.  Every failure degrades to "never read",
which costs rotation, never a run.
"""

import logging
import time

import redis

from app.config import settings

logger = logging.getLogger(__name__)

# Sync client on purpose: Celery tasks run via asyncio.run(), one event loop per
# task, so an async client would leak connections across loops.  The timeouts
# matter here: a sweep does one lookup per offered board (~170), and an
# unreachable Redis must not stall every one of them.
redis_client: redis.Redis = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)

#: How long a read is remembered. Long enough that a board which drops out of
#: the index for a week still counts as "recently read", short enough that a
#: board whose state is lost (Redis flushed) heals without a manual reset.
BOARD_SEEN_TTL_SECONDS = 30 * 24 * 3600
BOARD_SEEN_KEY = "ats_board_seen:{source}:{url}"

#: One warning per process: a sweep would otherwise log ~170 identical lines.
_warned = False


def _warn(action: str, error: Exception) -> None:
    global _warned
    if _warned:
        return
    _warned = True
    logger.warning("board_seen_%s_failed error=%s", action, error)


def _key(source_id: str, url: str) -> str:
    return BOARD_SEEN_KEY.format(source=source_id, url=url)


def board_last_seen(source_id: str | None, url: str) -> float | None:
    """When ``url`` was last read for this source, or ``None`` if unknown.

    ``None`` means the board is treated as unread, so it is read first: losing
    the memory costs a little rotation, but it must never cost the sweep.
    """
    if not source_id:
        return None
    try:
        value = redis_client.get(_key(source_id, url))
    except redis.RedisError as exc:
        _warn("lookup", exc)
        return None
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def board_mark_seen(
    source_id: str | None, url: str, *, ttl_seconds: int = BOARD_SEEN_TTL_SECONDS
) -> None:
    """Remember that ``url`` was read successfully by this source."""
    if not source_id:
        return
    try:
        redis_client.set(_key(source_id, url), str(time.time()), ex=max(1, ttl_seconds))
    except redis.RedisError as exc:
        _warn("store", exc)


def board_forget(source_id: str | None, url: str) -> None:
    """Forget a board's recency (``url`` died, or the caller wants a re-read)."""
    if not source_id:
        return
    try:
        redis_client.delete(_key(source_id, url))
    except redis.RedisError as exc:
        _warn("clear", exc)
