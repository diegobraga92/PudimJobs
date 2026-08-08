"""Celery Beat schedule.

A single periodic ``sweep_sources`` task runs every N minutes and enqueues a
``scrape_source`` task per source due for scraping. Per-source intervals are a
Phase-5 refinement; the sweep uses a uniform freshness threshold today.
"""

from app.config import settings

beat_schedule = {
    "sweep-sources": {
        "task": "workers.tasks.sweep.sweep_sources",
        "schedule": settings.scrape_sweep_interval_minutes * 60.0,
    },
}
