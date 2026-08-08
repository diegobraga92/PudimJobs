"""Long-running RabbitMQ consumer for ``job.new`` events.

Consumes messages from the ``matching.job.new`` queue (bound to the
``pudimjobs.events`` topic exchange on routing key ``job.new.#``) and enqueues
the ``match_job`` Celery task for each event. Run as its own process::

    python -m workers.consume_events
"""

import time

from app.config import settings
from kombu import Connection, Consumer, Exchange, Queue

from workers.celery_app import celery_app

EVENTS_EXCHANGE = Exchange("pudimjobs.events", type="topic", durable=True)
MATCHING_QUEUE = Queue(
    "matching.job.new", exchange=EVENTS_EXCHANGE, routing_key="job.new.#", durable=True
)


def _handle(body, message):
    job_id = body.get("job_id")
    if job_id:
        # One event, multiple consumers: alert matching + data quality.
        celery_app.send_task("workers.tasks.match.match_job", args=[job_id])
        celery_app.send_task("workers.tasks.quality.assess_quality", args=[job_id])
        print(f"enqueued match+quality for job {job_id}", flush=True)
    else:
        print("skipped event without job_id", flush=True)
    message.ack()


def run() -> None:
    print("job.new consumer starting...", flush=True)
    with Connection(settings.rabbitmq_url) as conn, Consumer(
        conn, queues=[MATCHING_QUEUE], callbacks=[_handle], accept=["json"]
    ):
        print("consuming job.new events (Ctrl+C to stop)", flush=True)
        while True:
            try:
                conn.drain_events(timeout=1)
            except TimeoutError:
                continue
            except Exception:  # noqa: BLE001 - keep the consumer alive
                time.sleep(1)


if __name__ == "__main__":
    run()
