"""Versioned event schemas and a RabbitMQ producer for PudimJobs."""

from api.events.producer import publish_job_new
from api.events.schemas import JobNewEvent

__all__ = ["JobNewEvent", "publish_job_new"]
