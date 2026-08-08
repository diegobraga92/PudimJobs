"""Task-enqueueing helper for the API.

Sends Celery tasks by name so the API can enqueue work (e.g. DLQ replay)
without importing the ``workers`` package. The worker consumes from the
default ``celery`` queue and dispatches by task name.
"""

from celery import Celery

from app.config import settings

_sender = Celery("pudimjobs-sender", broker=settings.celery_broker_url)

SCRAPE_TASK = "workers.tasks.scrape.scrape_source"


def enqueue_scrape(source_id: str) -> None:
    """Enqueue a ``scrape_source`` task for the given source id."""
    _sender.send_task(SCRAPE_TASK, args=[source_id])
