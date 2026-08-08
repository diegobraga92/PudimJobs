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


settings = Settings()