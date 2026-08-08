"""Tests for the sources CRUD API."""

from tests.helpers import create_user


async def test_list_sources_empty(auth_client):
    client, _, _ = auth_client
    response = await client.get("/api/sources")
    assert response.status_code == 200
    assert response.json() == []


async def test_create_source(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/sources",
        json={
            "name": "Acme Careers",
            "url": "https://acme.example/careers",
            "type": "career_page",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme Careers"
    assert body["type"] == "career_page"
    assert body["health"] == "healthy"
    assert body["id"]


async def test_crud_roundtrip(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={"name": "Agg", "url": "https://agg.example", "type": "aggregator"},
    )
    source_id = created.json()["id"]

    listed = await client.get("/api/sources")
    assert len(listed.json()) == 1

    updated = await client.put(f"/api/sources/{source_id}", json={"name": "Agg2"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Agg2"

    detail = await client.get(f"/api/sources/{source_id}")
    assert detail.json()["name"] == "Agg2"

    deleted = await client.delete(f"/api/sources/{source_id}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/sources/{source_id}")).status_code == 404


async def test_sources_require_auth(client):
    assert (await client.get("/api/sources")).status_code == 401


async def test_user_isolation(auth_client, db_client, db_session):
    """User B must not see sources created by user A."""
    client_a, _, _ = auth_client
    await client_a.post(
        "/api/sources",
        json={"name": "A's source", "url": "https://a.example", "type": "rss"},
    )

    user_b = await create_user(db_session, email="other@example.com")
    login = await db_client.post(
        "/api/auth/login", json={"email": user_b.email, "password": "password123"}
    )
    db_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    listed = await db_client.get("/api/sources")
    assert listed.json() == []
