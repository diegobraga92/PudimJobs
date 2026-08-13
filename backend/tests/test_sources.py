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
    # Scraping ethics defaults.
    assert body["rate_limit_seconds"] == 30
    assert body["respect_robots_txt"] is True


async def test_scraping_ethics_roundtrip(auth_client):
    """Per-source ethics settings survive create, read and update."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/sources",
        json={
            "name": "Polite Agg",
            "url": "https://agg.example",
            "type": "aggregator",
            "rate_limit_seconds": 60,
            "respect_robots_txt": False,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["rate_limit_seconds"] == 60
    assert body["respect_robots_txt"] is False

    source_id = body["id"]
    detail = await client.get(f"/api/sources/{source_id}")
    assert detail.json()["rate_limit_seconds"] == 60
    assert detail.json()["respect_robots_txt"] is False

    updated = await client.put(
        f"/api/sources/{source_id}",
        json={"rate_limit_seconds": 5, "respect_robots_txt": True},
    )
    assert updated.status_code == 200
    assert updated.json()["rate_limit_seconds"] == 5
    assert updated.json()["respect_robots_txt"] is True


async def test_scraping_ethics_validation(auth_client):
    """Negative/absurd rate limits are rejected by the API."""
    client, _, _ = auth_client
    for bad_payload in (
        {"rate_limit_seconds": -1},
        {"rate_limit_seconds": 86401},
    ):
        response = await client.post(
            "/api/sources",
            json={
                "name": "Bad",
                "url": "https://bad.example",
                "type": "rss",
                **bad_payload,
            },
        )
        assert response.status_code == 422


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


async def test_providers_endpoint_lists_discovery_providers(auth_client):
    client, _, _ = auth_client
    response = await client.get("/api/sources/providers")
    assert response.status_code == 200
    body = response.json()
    names = {provider["name"] for provider in body}
    # HTML-scraping providers were removed (ToS); the rest are present.
    assert {"ashby", "google_cse", "serpapi", "brightdata"} <= names
    assert not ({"google_html", "bing_html", "duckduckgo_html"} & names)

    for provider in body:
        assert set(provider) == {"name", "family", "requires_key"}

    ats = next(provider for provider in body if provider["name"] == "ashby")
    assert ats["family"] == "ats"
    assert ats["requires_key"] is False

    search = next(provider for provider in body if provider["name"] == "google_cse")
    assert search["family"] == "search_api"
    assert search["requires_key"] is True


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
