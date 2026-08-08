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
