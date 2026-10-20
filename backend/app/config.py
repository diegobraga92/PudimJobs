from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://pudimjobs:pudimjobs_dev@localhost:5432/pudimjobs"
    rabbitmq_url: str = "amqp://pudimjobs:pudimjobs_dev@localhost:5672/"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "DEBUG"

    # Auth / JWT
    secret_key: str = "dev-secret-key-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Encryption of secrets at rest (source credentials, LLM API keys).
    # Set FERNET_KEY to a Fernet key in production; a deterministic dev key is
    # derived from `secret_key` when this is empty (see app/services/secrets.py).
    fernet_key: str = ""

    # CV tailoring / optional LLM enhancement
    tailoring_llm_enabled: bool = False
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    # Max CV bullets rephrased per LLM call (ADR 006 rate limit).
    tailor_llm_max_bullets: int = 5
    # Cap on the CV + JD payload sent to the full-rewrite LLM call (ADR 016).
    tailor_llm_max_chars: int = 12_000

    # Notifications / email (Mailpit for local dev)
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "PudimJobs <alerts@pudimjobs.dev>"
    smtp_username: str = ""
    smtp_password: str = ""
    notification_from_name: str = "PudimJobs"
    in_app_notification_enabled: bool = True

    # Observability
    otlp_endpoint: str = ""  # e.g. http://jaeger:4318/v1/traces (empty = disabled)
    worker_metrics_port: int = 0  # 0 = worker /metrics server disabled

    # CORS: comma-separated browser origins allowed to call the API directly.
    # The Angular dev server proxies /api internally (same origin), so the UI
    # does not depend on this — it matters for direct browser access to the API
    # (e.g. Swagger UI at /docs) from other hosts. Set via CORS_ORIGINS.
    cors_origins: str = (
        "http://localhost:4200,http://127.0.0.1:4200,http://localhost:9400,http://127.0.0.1:9400"
    )

    # Rate limiting (slowapi)
    rate_limit_login: str = "5/minute"
    rate_limit_api: str = "120/minute"
    # Source preview runs a scraper synchronously inside the API process, so it
    # is throttled harder than the rest of the API.
    rate_limit_preview: str = "20/minute"

    # Celery / workers
    celery_broker_url: str = "amqp://pudimjobs:pudimjobs_dev@localhost:5672/"
    celery_result_backend: str = "redis://localhost:6379/1"
    worker_concurrency: int = 4
    worker_prefetch_multiplier: int = 1

    # Scrape task runtime limits. RabbitMQ only acknowledges a task when it
    # finishes (task_acks_late=True); if a run outlives the broker's
    # consumer_timeout the broker kills the worker's connection and the queue
    # stalls. Celery therefore fails the task first, below the broker timeout
    # (see infra/rabbitmq/rabbitmq.conf), so the failure is recorded on the
    # ScrapeRun instead of silently orphaning the consumer.
    scrape_task_soft_time_limit_seconds: int = 1200  # 20 min
    scrape_task_time_limit_seconds: int = 1500  # 25 min
    # Stop stale queued work: a task that waited longer than this is redundant
    # because the next sweep has already rebuilt the due list.
    scrape_task_expires_seconds: int = 1800  # 30 min
    # A run left in "running" after this long is orphaned (worker killed or it
    # lost the broker connection); the sweep fails it and schedules fresh work.
    scrape_run_stale_minutes: int = 30
    # After a source is skipped (robots.txt, missing API key, ...), do not
    # re-enqueue it on every sweep. The backoff expires on its own; an explicit
    # "Scrape now" still runs immediately.
    scrape_skip_backoff_minutes: int = 1440  # 24 h
    # A *transient* skip (robots.txt unreachable: timeout, 5xx, DNS blip) is
    # retried much sooner than a permanent one (an explicit robots.txt
    # ``Disallow``). Long enough to skip the current sweep, short enough that a
    # network blip does not freeze a healthy source for a day.
    scrape_skip_retry_minutes: int = 15

    # Scraping defaults
    circuit_breaker_threshold: int = 5
    circuit_breaker_ttl_seconds: int = 3600  # pause for 1h when open
    scrape_sweep_interval_minutes: int = 15
    scrape_freshness_minutes: int = 60  # sources fresher than this are skipped
    # Allow scraping private/loopback targets (e.g. a LAN-hosted careers site).
    # Off by default to keep shared deployments SSRF-safe.
    scraper_allow_private_networks: bool = False
    # SSRF hardening: cap each response body and the redirect chain length.
    scraper_max_response_bytes: int = 2_000_000  # 2 MB
    scraper_max_redirects: int = 5
    # Source preview: jobs returned in the sample, and how long the in-process
    # run may take before the request gives up.
    scraper_preview_max_jobs: int = 5
    scraper_preview_timeout_seconds: float = 20.0
    # Bot identity used when matching robots.txt rules (not the HTTP request UA,
    # which stays browser-like for anti-bot compatibility).
    scraper_bot_user_agent: str = "PudimJobsBot/0.1"
    user_agents: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36,"
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15,"
        "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"
    )


settings = Settings()
