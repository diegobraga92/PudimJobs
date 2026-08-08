"""Versioned event schemas and a RabbitMQ producer for PudimJobs.

Events are published to the ``pudimjobs.events`` topic exchange. Every event
carries a ``version`` field; consumers must tolerate newer payloads that are a
strict superset of the versions they understand (additive-only changes).
"""

from api.events.producer import publish_job_new
from api.events.schemas import JobNewEvent

__all__ = ["JobNewEvent", "publish_job_new"]
