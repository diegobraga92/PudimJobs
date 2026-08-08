"""Tests for the jobs API (manual CRUD + search/filter)."""


async def test_create_job_manual(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/jobs",
        json={
            "title": "Senior Python Engineer",
            "company": "Acme",
            "description": "Build APIs with FastAPI.",
            "url": "https://acme.example/jobs/1",
            "tags": ["python", "fastapi"],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Senior Python Engineer"
    assert body["tags"] == ["python", "fastapi"]
    assert body["source_id"] is None


async def test_job_search_filters(auth_client):
    client, _, _ = auth_client
    for payload in [
        {
            "title": "Backend Engineer",
            "company": "Acme",
            "description": "Python and Postgres",
            "tags": ["python"],
        },
        {
            "title": "Frontend Engineer",
            "company": "Beta",
            "description": "TypeScript and Angular",
            "tags": ["angular"],
        },
    ]:
        response = await client.post("/api/jobs", json=payload)
        assert response.status_code == 201

    by_keyword = await client.get("/api/jobs", params={"q": "backend"})
    assert len(by_keyword.json()) == 1
    assert by_keyword.json()[0]["company"] == "Acme"

    by_company = await client.get("/api/jobs", params={"company": "beta"})
    assert len(by_company.json()) == 1
    assert by_company.json()[0]["company"] == "Beta"

    by_tags = await client.get("/api/jobs", params={"tags": "python"})
    assert len(by_tags.json()) == 1

    no_match = await client.get("/api/jobs", params={"q": "rust"})
    assert no_match.json() == []


async def test_create_job_with_foreign_source_rejected(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/jobs",
        json={
            "title": "X",
            "company": "Y",
            "source_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert response.status_code == 404


async def test_job_detail_includes_description(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/jobs",
        json={"title": "SRE", "company": "Acme", "description": "On-call rotations"},
    )
    job_id = created.json()["id"]

    detail = await client.get(f"/api/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["description"] == "On-call rotations"


async def test_jobs_require_auth(client):
    assert (await client.get("/api/jobs")).status_code == 401
