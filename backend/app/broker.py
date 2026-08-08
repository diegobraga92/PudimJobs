"""Task-enqueueing helper for the API.

Sends Celery tasks by name so the API can enqueue work (e.g. DLQ replay, JD
parsing, CV tailoring) without importing the ``workers`` package. The worker
consumes from the default ``celery`` queue and dispatches by task name.
"""

from celery import Celery

from app.config import settings

_sender = Celery("pudimjobs-sender", broker=settings.celery_broker_url)

SCRAPE_TASK = "workers.tasks.scrape.scrape_source"
PARSE_JD_TASK = "workers.tasks.jd_parse.parse_jd_task"
TAILOR_CV_TASK = "workers.tasks.tailor.tailor_cv_task"


def enqueue_scrape(source_id: str) -> None:
    """Enqueue a ``scrape_source`` task for the given source id."""
    _sender.send_task(SCRAPE_TASK, args=[source_id])


def enqueue_parse_jd(job_id: str) -> None:
    """Enqueue a JD parsing task for the given job id."""
    _sender.send_task(PARSE_JD_TASK, args=[job_id])


def enqueue_tailor(job_id: str, cv_id: str | None = None) -> None:
    """Enqueue a CV tailoring task; ``cv_id=None`` uses the current CV."""
    _sender.send_task(TAILOR_CV_TASK, args=[job_id, cv_id])

