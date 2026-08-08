"""Shared pytest fixtures for the PudimJobs backend.

Two client fixtures are provided:

- ``client``     — plain in-process HTTP client (no DB); used for /health tests.
- ``db_client``  — HTTP client with the DB dependency overridden to a dedicated
                  test database; used by integration tests.

Integration tests require a reachable PostgreSQL test database (defaults to
``postgresql+asyncpg://pudimjobs:pudimjobs_test@localhost:5433/pudimjobs_test``,
override with the ``TEST_DATABASE_URL`` environment variable). Worker/scraper
tests additionally need Redis (default ``redis://localhost:6380/0``).
When these services are unavailable the relevant tests are skipped.
"""

import os

# Configure shared settings BEFORE importing the application so the app engine,
# Celery app and resilience Redis client target the test services.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://pudimjobs:pudimjobs_test@localhost:5433/pudimjobs_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/0")
os.environ.setdefault("RABBITMQ_URL", "amqp://pudimjobs:pudimjobs_dev@localhost:5673/")
os.environ.setdefault("CELERY_BROKER_URL", "amqp://pudimjobs:pudimjobs_dev@localhost:5673/")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database import get_db
from app.main import app
from app.models import Base
from tests.helpers import create_user

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://pudimjobs:pudimjobs_test@localhost:5433/pudimjobs_test",
)


# --- Test database ----------------------------------------------------------


@pytest.fixture
async def test_engine():
    """Fresh schema in the test database for the duration of one test."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - environment without a test DB
        pytest.skip(f"Test database unavailable ({exc}); skipping integration tests")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine):
    """A session bound to the (freshly created) test database."""
    session = async_sessionmaker(test_engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture
async def db_client(test_engine):
    """HTTP client whose ``get_db`` dependency targets the test database."""

    async def override_get_db():
        async with async_sessionmaker(test_engine, expire_on_commit=False)() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# --- Redis (worker/resilience tests) ----------------------------------------


@pytest.fixture
def redis_client():
    """A connected sync Redis client; skips tests when Redis is unavailable."""
    try:
        import redis as redis_lib

        client = redis_lib.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
        client.ping()
    except Exception as exc:  # noqa: BLE001 - environment without Redis
        pytest.skip(f"Redis unavailable ({exc}); skipping worker tests")
    yield client
    client.flushdb()
    client.close()


# --- Plain client for non-DB tests ------------------------------------------


@pytest.fixture
async def client():
    """An in-process async HTTP client for the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Helpers ----------------------------------------------------------------


@pytest.fixture
async def auth_client(db_client, db_session):
    """A client authenticated as a fresh user.

    Yields ``(client, user, token)``.
    """
    user = await create_user(db_session)
    response = await db_client.post(
        "/api/auth/login", json={"email": user.email, "password": "password123"}
    )
    token = response.json()["access_token"]
    db_client.headers["Authorization"] = f"Bearer {token}"
    return db_client, user, token

