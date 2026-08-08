"""Shared pytest fixtures for the PudimJobs backend.

Uses httpx's ASGITransport to exercise the FastAPI application in-process,
without requiring a live database, RabbitMQ, or Redis.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """An in-process async HTTP client for the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
