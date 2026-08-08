"""Tests for the /health endpoint and /metrics endpoint."""

from app import main


async def test_health_ok_when_db_connected(client, monkeypatch):
    """A healthy database connection should yield 200 / ok / connected."""

    async def _db_healthy() -> bool:
        return True

    monkeypatch.setattr(main, "check_db_health", _db_healthy)

    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "connected"
    assert "timestamp" in body


async def test_health_degraded_when_db_down(client, monkeypatch):
    """An unavailable database should yield 503 / degraded / disconnected."""

    async def _db_down() -> bool:
        return False

    monkeypatch.setattr(main, "check_db_health", _db_down)

    response = await client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] == "disconnected"
    assert "timestamp" in body


async def test_health_returns_trace_id_header(client, monkeypatch):
    """Every response should carry an X-Trace-Id header for correlation."""

    async def _db_healthy() -> bool:
        return True

    monkeypatch.setattr(main, "check_db_health", _db_healthy)

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.headers.get("X-Trace-Id")


async def test_metrics_endpoint_exposed(client):
    """The Prometheus /metrics endpoint should be available."""
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
