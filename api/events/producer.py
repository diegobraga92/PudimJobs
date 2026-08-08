"""RabbitMQ event producer.

Uses kombu (already a Celery dependency) to publish ``job.new`` events to the
``pudimjobs.events`` topic exchange. Connection strings come from
``app.config.settings`` so workers and the API share one configuration.
"""

import logging

from app.config import settings
from kombu import Connection, Exchange

from api.events.schemas import JobNewEvent

logger = logging.getLogger(__name__)

EVENTS_EXCHANGE = Exchange("pudimjobs.events", type="topic", durable=True)


def publish_job_new(event: JobNewEvent) -> None:
    """Publish a ``job.new`` event to RabbitMQ (routing key ``job.new``)."""
    routing_key = f"job.new.v{event.version}"
    try:
        with Connection(settings.rabbitmq_url) as conn:
            producer = conn.Producer()
            producer.publish(
                event.model_dump(mode="json"),
                exchange=EVENTS_EXCHANGE,
                routing_key=routing_key,
                serializer="json",
                retry=True,
                retry_policy={
                    "max_retries": 3,
                    "interval_start": 0,
                    "interval_step": 1,
                    "interval_max": 5,
                },
                declare=[EVENTS_EXCHANGE],
            )
    except Exception:
        logger.exception("Failed to publish job.new event for job %s", event.job_id)
