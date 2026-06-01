from prometheus_fastapi_instrumentator import Instrumentator


def setup_metrics(app) -> Instrumentator:
    """Configure and attach Prometheus metrics to the FastAPI app.

    Exposes:
    - Default HTTP metrics (request count, latency histogram, error rate)
    - Can be extended with custom metrics later
    """
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
    )
    instrumentator.instrument(app).expose(app)
    return instrumentator