from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://pudimjobs:pudimjobs_dev@localhost:5432/pudimjobs"
    rabbitmq_url: str = "amqp://pudimjobs:pudimjobs_dev@localhost:5672/"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "DEBUG"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()