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

    # CV tailoring / optional LLM enhancement
    tailoring_llm_enabled: bool = False
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

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
        "http://localhost:4200,http://127.0.0.1:4200,"
        "http://localhost:9400,http://127.0.0.1:9400"
    )

    # Rate limiting (slowapi)
    rate_limit_login: str = "5/minute"
    rate_limit_api: str = "120/minute"

    # Celery / workers
    celery_broker_url: str = "amqp://pudimjobs:pudimjobs_dev@localhost:5672/"
    celery_result_backend: str = "redis://localhost:6379/1"
    worker_concurrency: int = 4
    worker_prefetch_multiplier: int = 1

    # Scraping defaults
    circuit_breaker_threshold: int = 5
    circuit_breaker_ttl_seconds: int = 3600  # pause for 1h when open
    scrape_sweep_interval_minutes: int = 15
    scrape_freshness_minutes: int = 60  # sources fresher than this are skipped
    user_agents: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36,"
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15,"
        "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"
    )


settings = Settings()
