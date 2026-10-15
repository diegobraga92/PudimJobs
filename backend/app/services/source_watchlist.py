"""Manual watchlist sources: cadence, due dates and reminders (ADR 018).

A ``manual`` source is a job board the engine cannot scrape automatically
(login-walled SPA, anti-bot API, directory). It is never fetched by the
sweeper; instead the user re-checks it by hand and the app reminds them when
it is due. The derived watchlist state lives in ``source.config`` so no extra
column (and no migration) is required:

- ``cadence_days``  — how often to re-check (default
  :data:`DEFAULT_CADENCE_DAYS`, accepted range :data:`MIN_CADENCE_DAYS`
  .. :data:`MAX_CADENCE_DAYS`; published by ``GET /api/sources/manual-metadata``).
- ``notes``         — free-form reminder of what to look for by hand (optional).
- ``next_check_at`` — ISO timestamp; written by
  :func:`advance_manual_check`, optional as a manual override.
- ``reminded_at``   — ISO timestamp of the last reminder (internal; cleared on
  check) so a due source is reminded about once per period, not every sweep.

The *avoid* flag (ADR 019) is the one watchlist state that is **not** config:
it applies to every source type and is queryable by the sweeper, so it lives in
the dedicated ``sources.avoided_at``/``avoid_reason`` columns.
"""

from datetime import UTC, datetime, timedelta

from app.models.enums import SourceHealth

DEFAULT_CADENCE_DAYS = 7
MIN_CADENCE_DAYS = 1
MAX_CADENCE_DAYS = 365


def _parse_dt(value: object) -> datetime | None:
    """Parse an ISO timestamp from config, tolerating junk and naive values."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def cadence_days(config: dict | None) -> int:
    """The re-check cadence in days, clamped to a sane range."""
    raw = (config or {}).get("cadence_days", DEFAULT_CADENCE_DAYS)
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_CADENCE_DAYS
    return max(MIN_CADENCE_DAYS, min(days, MAX_CADENCE_DAYS))


def next_check_at(source) -> datetime | None:
    """When the source is next due, or ``None`` for non-manual sources."""
    from app.models.enums import SourceType

    if source.type != SourceType.manual:
        return None
    config = source.config or {}
    explicit = _parse_dt(config.get("next_check_at"))
    if explicit is not None:
        return explicit
    base = _parse_dt(source.last_scraped) or _parse_dt(source.created_at)
    if base is None:
        return None
    return base + timedelta(days=cadence_days(config))


def is_due(source, now: datetime | None = None) -> bool:
    """True when a manual source should be re-checked by the user.

    Avoided sources are never due: the user explicitly asked to stop being
    reminded about them (ADR 019).
    """
    from app.models.enums import SourceType

    if source.type != SourceType.manual or is_avoided(source):
        return False
    due = next_check_at(source)
    if due is None:
        return True
    return due <= (now or datetime.now(UTC))


def is_avoided(source) -> bool:
    """True when the user flagged the source as *avoid* (ADR 019).

    Avoided sources are never fetched and never reminded about — for every
    source type — but they stay listed so they remain a visible reminder.
    """
    return getattr(source, "avoided_at", None) is not None


def set_avoided(
    source, avoided: bool, reason: str | None = None, now: datetime | None = None
) -> None:
    """Flag a source as avoided, or restore it (ADR 019).

    Mutates the ORM instance in place; the caller commits. Re-avoiding an
    already-avoided source keeps the original ``avoided_at``, so the timestamp
    means "avoided since" and the toggle stays idempotent. An omitted ``reason``
    (``None``) also keeps the stored one, so a one-click re-avoid cannot wipe
    it; pass an empty string to clear it while staying avoided.

    ``next_check_at`` is deliberately left untouched so restoring reveals the
    true schedule; ``reminded_at`` is cleared on restore so an overdue source
    nudges exactly once more instead of silently staying quiet.
    """
    moment = now or datetime.now(UTC)
    if avoided:
        source.avoided_at = source.avoided_at or moment
        if reason is not None:
            source.avoid_reason = reason.strip() or None
        return

    source.avoided_at = None
    source.avoid_reason = None
    config = dict(source.config or {})
    if config.pop("reminded_at", None) is not None:
        source.config = config


def was_reminded(source) -> bool:
    """True when a reminder was already sent for the current due period."""
    return _parse_dt((source.config or {}).get("reminded_at")) is not None


def advance_manual_check(source, now: datetime | None = None) -> None:
    """Stamp a manual source as checked and schedule the next reminder.

    Mutates the ORM instance in place; the caller commits.
    """
    moment = now or datetime.now(UTC)
    config = dict(source.config or {})
    config["next_check_at"] = (
        moment + timedelta(days=cadence_days(config))
    ).isoformat()
    config.pop("reminded_at", None)
    source.config = config
    source.last_scraped = moment
    source.health = SourceHealth.healthy


def mark_reminded(source, now: datetime | None = None) -> None:
    """Record that a reminder was sent for the current due period.

    Mutates the ORM instance in place; the caller commits.
    """
    config = dict(source.config or {})
    config["reminded_at"] = (now or datetime.now(UTC)).isoformat()
    source.config = config
