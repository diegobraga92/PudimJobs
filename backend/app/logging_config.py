import logging

import structlog


def silence_httpx_request_logs() -> None:
    """Keep vendor API keys out of logs.

    httpx logs every request URL at INFO, and paid providers put their key in
    the query string (SerpApi's ``api_key``, Google CSE's ``key``). Those logs
    would persist a live secret, so vendor HTTP request logging stays at
    WARNING (errors still surface).
    """
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def configure_logging(log_level: str = "DEBUG") -> None:
    """Configure structured JSON logging with structlog."""
    silence_httpx_request_logs()
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler()
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            *shared_processors,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())
