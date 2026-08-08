"""OpenTelemetry setup shared by the API and the workers.

Exporters send spans to an OTLP endpoint (e.g. Jaeger). When
``settings.otlp_endpoint`` is empty, telemetry is a no-op so tests and local
runs without a collector are unaffected.
"""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings


def init_telemetry(service_name: str) -> trace.Tracer | None:
    """Initialise the global tracer provider; returns a tracer or None."""
    if not settings.otlp_endpoint:
        return None
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint))
    )
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)
