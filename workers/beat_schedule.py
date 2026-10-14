"""Celery Beat schedule."""

from app.config import settings

beat_schedule = {
    "sweep-sources": {
        "task": "workers.tasks.sweep.sweep_sources",
        "schedule": settings.scrape_sweep_interval_minutes * 60.0,
    },
}
