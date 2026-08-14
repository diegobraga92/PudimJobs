"""Tests for application settings loading."""

from app.config import Settings


def test_default_settings_are_sensible():
    settings = Settings()

    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.rabbitmq_url.startswith("amqp://")
    assert settings.redis_url.startswith("redis://")
    assert settings.log_level == "DEBUG"
    assert settings.scraper_max_response_bytes == 2_000_000
    assert settings.scraper_max_redirects == 5
    assert settings.scraper_bot_user_agent == "PudimJobsBot/0.1"
    assert settings.tailor_llm_max_bullets == 5


def test_settings_override_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://override:5432/pudimjobs")
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    settings = Settings()

    assert settings.database_url == "postgresql+asyncpg://override:5432/pudimjobs"
    assert settings.log_level == "INFO"
