"""Tests for the admin API (RBAC + reprocessing endpoints)."""

from app.models import ScrapeRun, Source
from tests.helpers import create_user


async def _login(db_client, email: str) -> None:
    response = await db_client.post(
        "/api/auth/login", json={"email": email, "password": "password123"}
    )
    db_client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"


async def _make_admin(db_client, db_session):
    user = await create_user(db_session, email="admin@example.com", role="admin")
    await _login(db_client, user.email)
    return user


async def test_admin_endpoints_reject_regular_user(auth_client):
    client, _, _ = auth_client
    assert (await client.get("/api/admin/stats")).status_code == 403
    assert (await client.get("/api/admin/sources/health")).status_code == 403
    assert (await client.get("/api/admin/dlq")).status_code == 403


async def test_admin_stats(db_client, db_session):
    await _make_admin(db_client, db_session)
    response = await db_client.get("/api/admin/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == 0
    assert body["jobs"] == 0
    assert "failed_runs" in body


async def test_admin_source_health(db_client, db_session):
    await _make_admin(db_client, db_session)
    user = await create_user(db_session, email="owner@example.com")
    source = Source(user_id=user.id, name="Acme", url="https://acme.example", type="rss")
    db_session.add(source)
    await db_session.commit()

    response = await db_client.get("/api/admin/sources/health")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "Acme"


async def test_replay_failed_run(db_client, db_session, monkeypatch):
    await _make_admin(db_client, db_session)
    user = await create_user(db_session, email="owner2@example.com")
    source = Source(user_id=user.id, name="Beta", url="https://beta.example", type="rss")
    db_session.add(source)
    await db_session.commit()

    run = ScrapeRun(source_id=source.id, status="failed", error="boom", new_jobs=0)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    enqueued: list[str] = []
    monkeypatch.setattr("app.routers.admin.enqueue_scrape", enqueued.append)

    response = await db_client.post(f"/api/admin/dlq/{run.id}/replay")
    assert response.status_code == 200
    assert response.json()["replayed"] is True
    assert enqueued == [str(source.id)]


async def test_replay_missing_run(db_client, db_session):
    await _make_admin(db_client, db_session)
    response = await db_client.post(
        "/api/admin/dlq/00000000-0000-0000-0000-000000000000/replay"
    )
    assert response.status_code == 404
