from prometheus_fastapi_instrumentator import Instrumentator


def setup_metrics(app) -> Instrumentator:
    """Configure and attach Prometheus metrics to the FastAPI app."""
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
    )
    instrumentator.instrument(app).expose(app)
    return instrumentator
