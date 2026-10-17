"""Per-source scrape scheduling.

A source may set ``scrape_interval_minutes`` to be scraped less often than the
global sweep freshness. The global value is a hard floor: it keeps the old
behaviour for sources with no interval and prevents a very small per-source
value from making the sweeper fetch a board on every beat.
"""

from datetime import UTC, datetime, timedelta

from app.config import settings
from app.models.enums import SourceType


def effective_scrape_interval_minutes(source) -> int:
    """Minutes between runs for ``source`` (global freshness acting as a floor)."""
    return max(settings.scrape_freshness_minutes, source.scrape_interval_minutes or 0)


def _as_utc(value: datetime) -> datetime:
    """Normalize a timestamp so naive values from tests/backends compare safely."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def is_scrape_due(source, now: datetime | None = None) -> bool:
    """True when the sweeper may enqueue ``source`` for a scrape.

    Manual sources are hand-checked, never scraped. A source with no recorded
    run is always due; otherwise it waits for its effective interval.
    """
    if source.type == SourceType.manual:
        return False
    if source.last_scraped is None:
        return True
    now = now or datetime.now(UTC)
    interval = effective_scrape_interval_minutes(source)
    return _as_utc(source.last_scraped) <= _as_utc(now) - timedelta(minutes=interval)


def next_scrape_at(source) -> datetime | None:
    """When the source becomes due again, or ``None`` when it never ran.

    The value may be in the past (a source waiting for the next sweep); callers
    can pair it with :func:`is_scrape_due` to render "due now" instead of a date.
    """
    if source.type == SourceType.manual or source.last_scraped is None:
        return None
    interval = effective_scrape_interval_minutes(source)
    return _as_utc(source.last_scraped) + timedelta(minutes=interval)
