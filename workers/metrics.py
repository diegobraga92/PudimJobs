"""Prometheus metrics for the scraping workers.

Started as a daemon HTTP server (default port 9100) so the worker process can
be scraped without exposing an HTTP framework.
"""

from prometheus_client import Counter, Gauge, Histogram, start_http_server

SCRAPES_TOTAL = Counter(
    "pudimjobs_scrapes_total",
    "Scrape attempts by source and status",
    ["source_id", "status"],
)
SCRAPE_DURATION = Histogram(
    "pudimjobs_scrape_duration_seconds",
    "Duration of a scrape task",
    ["source_id"],
)
DLQ_SIZE = Gauge("pudimjobs_dlq_size", "Number of failed scrape runs")
CIRCUIT_BREAKER_OPEN = Gauge(
    "pudimjobs_circuit_breaker_open", "Open circuit breakers", ["source_id"]
)


def start_metrics_server(port: int = 9100) -> None:
    start_http_server(port)
