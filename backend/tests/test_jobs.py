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


async def test_hidden_jobs_excluded_by_default_and_toggleable(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/jobs",
        json={"title": "Secret Ops", "company": "Acme", "description": "Hidden work"},
    )
    assert created.status_code == 201
    job_id = created.json()["id"]
    assert created.json()["hidden"] is False

    # Toggle hidden on via the update endpoint.
    hidden = await client.put(f"/api/jobs/{job_id}", json={"hidden": True})
    assert hidden.status_code == 200
    assert hidden.json()["hidden"] is True

    # Hidden jobs are excluded from the default listing…
    listed = await client.get("/api/jobs")
    assert all(job["id"] != job_id for job in listed.json())

    # …but returned when include_hidden is requested.
    with_hidden = await client.get("/api/jobs", params={"include_hidden": "true"})
    assert any(job["id"] == job_id and job["hidden"] is True for job in with_hidden.json())

    # And they can be unhidden again.
    visible = await client.put(f"/api/jobs/{job_id}", json={"hidden": False})
    assert visible.json()["hidden"] is False
    listed = await client.get("/api/jobs")
    assert any(job["id"] == job_id for job in listed.json())


async def test_hide_applied_filters_out_applied_jobs(auth_client):
    client, _, _ = auth_client
    await client.post("/api/jobs", json={"title": "Plain", "company": "Acme"})
    saved = (await client.post("/api/jobs", json={"title": "Saved", "company": "Beta"})).json()
    applied = (await client.post("/api/jobs", json={"title": "Applied", "company": "Gamma"})).json()

    # "saved" is a bookmark — the job stays visible; "applied" should be hidden.
    await client.post("/api/applications", json={"job_id": saved["id"], "status": "saved"})
    await client.post("/api/applications", json={"job_id": applied["id"], "status": "applied"})

    filtered = await client.get("/api/jobs", params={"hide_applied": "true"})
    titles = [job["title"] for job in filtered.json()]
    assert "Applied" not in titles
    assert "Saved" in titles
    assert "Plain" in titles

    # Without the filter every job is present again.
    unfiltered = await client.get("/api/jobs")
    assert len(unfiltered.json()) == 3


async def test_hide_applied_applies_to_keyword_search(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/jobs",
        json={"title": "Backend Engineer", "company": "Acme", "description": "Python API"},
    )
    job_id = created.json()["id"]
    await client.post("/api/applications", json={"job_id": job_id, "status": "interview"})

    without = await client.get("/api/jobs", params={"q": "backend", "hide_applied": "true"})
    assert without.json() == []

    with_filter_off = await client.get(
        "/api/jobs", params={"q": "backend", "hide_applied": "false"}
    )
    assert len(with_filter_off.json()) == 1

