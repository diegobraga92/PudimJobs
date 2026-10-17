"""Unit tests for per-source scrape scheduling (no database required)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.config import settings
from app.models.enums import SourceType
from app.services.source_schedule import (
    effective_scrape_interval_minutes,
    is_scrape_due,
    next_scrape_at,
)


def _source(**overrides) -> SimpleNamespace:
    values = {
        "type": SourceType.rss,
        "scrape_interval_minutes": None,
        "last_scraped": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_global_freshness_is_a_floor(monkeypatch):
    monkeypatch.setattr(settings, "scrape_freshness_minutes", 60)

    assert effective_scrape_interval_minutes(_source()) == 60
    assert effective_scrape_interval_minutes(_source(scrape_interval_minutes=360)) == 360
    # A smaller per-source value cannot make the sweeper fetch more often.
    assert effective_scrape_interval_minutes(_source(scrape_interval_minutes=5)) == 60


def test_due_checks_use_the_effective_interval(monkeypatch):
    monkeypatch.setattr(settings, "scrape_freshness_minutes", 60)
    now = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

    never_scraped = _source()
    recent_hourly = _source(last_scraped=now - timedelta(minutes=30))
    stale_hourly = _source(last_scraped=now - timedelta(minutes=90))
    recent_weekly = _source(
        scrape_interval_minutes=10080,
        last_scraped=now - timedelta(days=2),
    )
    stale_weekly = _source(
        scrape_interval_minutes=10080,
        last_scraped=now - timedelta(days=8),
    )

    assert is_scrape_due(never_scraped, now) is True
    assert is_scrape_due(recent_hourly, now) is False
    assert is_scrape_due(stale_hourly, now) is True
    assert is_scrape_due(recent_weekly, now) is False
    assert is_scrape_due(stale_weekly, now) is True


def test_manual_sources_are_never_scrape_due(monkeypatch):
    monkeypatch.setattr(settings, "scrape_freshness_minutes", 60)
    source = _source(type=SourceType.manual, last_scraped=datetime(2020, 1, 1, tzinfo=UTC))

    assert is_scrape_due(source) is False
    assert next_scrape_at(source) is None


def test_next_scrape_at_is_last_run_plus_interval(monkeypatch):
    monkeypatch.setattr(settings, "scrape_freshness_minutes", 60)
    last_scraped = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    source = _source(scrape_interval_minutes=1440, last_scraped=last_scraped)

    assert next_scrape_at(source) == last_scraped + timedelta(days=1)
    assert next_scrape_at(_source()) is None
