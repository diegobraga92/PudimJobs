"""Celery application for PudimJobs workers.

The broker is RabbitMQ (enables durable queues and broker-level dead-letter
exchanges); Redis is the result backend and stores circuit-breaker state.
"""

from app.config import settings
from celery import Celery
from kombu import Exchange, Queue

# Broker-level dead-letter topology: tasks that are rejected or expire land in
# the ``pudimjobs.dlx`` queue so they can be inspected and replayed.
DLX_EXCHANGE = Exchange("pudimjobs.dlx", type="direct", durable=True)
DLX_QUEUE = Queue(
    "pudimjobs.dlx",
    DLX_EXCHANGE,
    routing_key="scrape.failed",
    durable=True,
)

celery_app = Celery(
    "pudimjobs",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["workers.tasks.scrape", "workers.tasks.sweep"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_concurrency=settings.worker_concurrency,
    worker_prefetch_multiplier=settings.worker_prefetch_multiplier,
    # Rejected/lost tasks are routed to the DLX instead of being lost.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_transport_options={"visibility_timeout": 3600},
    # Beat schedule (sweep task that enqueues per-source scrapes).
    beat_schedule={
        "sweep-sources": {
            "task": "workers.tasks.sweep.sweep_sources",
            "schedule": settings.scrape_sweep_interval_minutes * 60.0,
        },
    },
)
