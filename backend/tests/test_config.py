"""Tests for application settings loading."""

import logging

from app.config import Settings
from app.logging_config import silence_httpx_request_logs


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
    assert settings.tailor_llm_max_chars == 12_000


def test_settings_override_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://override:5432/pudimjobs")
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    settings = Settings()

    assert settings.database_url == "postgresql+asyncpg://override:5432/pudimjobs"
    assert settings.log_level == "INFO"


def test_httpx_request_logs_are_silenced():
    """Vendor URLs carry API keys; httpx request logging must stay at WARNING."""
    vendor_loggers = [logging.getLogger("httpx"), logging.getLogger("httpcore")]
    original_levels = [logger.level for logger in vendor_loggers]
    try:
        for logger in vendor_loggers:
            logger.setLevel(logging.DEBUG)

        silence_httpx_request_logs()

        assert all(logger.level == logging.WARNING for logger in vendor_loggers)
    finally:
        for logger, level in zip(vendor_loggers, original_levels, strict=True):
            logger.setLevel(level)
