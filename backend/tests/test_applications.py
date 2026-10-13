"""Tests for the applications pipeline API."""

from sqlalchemy import select

from app.models.audit_log import AuditLog


async def _create_job(client) -> dict:
    response = await client.post(
        "/api/jobs",
        json={"title": "Data Engineer", "company": "Acme", "description": "ETL pipelines"},
    )
    assert response.status_code == 201
    return response.json()


async def test_create_and_update_application(auth_client):
    client, _, _ = auth_client
    job = await _create_job(client)

    created = await client.post("/api/applications", json={"job_id": job["id"], "status": "saved"})
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "saved"
    assert body["job_title"] == "Data Engineer"
    assert body["job_company"] == "Acme"

    updated = await client.put(f"/api/applications/{body['id']}", json={"status": "interview"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "interview"


async def test_list_applications_filter_by_status(auth_client):
    client, _, _ = auth_client
    job = await _create_job(client)
    application_id = (await client.post("/api/applications", json={"job_id": job["id"]})).json()[
        "id"
    ]
    await client.put(f"/api/applications/{application_id}", json={"status": "offer"})

    saved = await client.get("/api/applications", params={"status_filter": "saved"})
    assert saved.json() == []

    offer = await client.get("/api/applications", params={"status_filter": "offer"})
    assert len(offer.json()) == 1
    assert offer.json()[0]["job_title"] == "Data Engineer"


async def test_application_requires_owned_job(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/applications",
        json={"job_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


async def test_status_change_is_audited(auth_client, db_session):
    client, _, _ = auth_client
    job = await _create_job(client)
    application_id = (await client.post("/api/applications", json={"job_id": job["id"]})).json()[
        "id"
    ]
    await client.put(f"/api/applications/{application_id}", json={"status": "applied"})

    result = await db_session.execute(select(AuditLog).where(AuditLog.entity_type == "application"))
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].action == "updated"
    assert entries[0].changes["status"] == {"before": "saved", "after": "applied"}


async def test_lessons_endpoint_lists_only_retrospectives(auth_client):
    client, _, _ = auth_client
    job = await _create_job(client)

    with_lessons = (
        await client.post(
            "/api/applications",
            json={"job_id": job["id"], "lessons_learned": "Ask about on-call rotation earlier."},
        )
    ).json()
    assert with_lessons["lessons_learned"] == "Ask about on-call rotation earlier."
    await client.post("/api/applications", json={"job_id": job["id"]})

    response = await client.get("/api/applications/lessons")

    assert response.status_code == 200
    entries = response.json()
    assert [entry["application_id"] for entry in entries] == [with_lessons["id"]]
    assert entries[0]["job_title"] == "Data Engineer"
    assert entries[0]["job_company"] == "Acme"
    assert entries[0]["status"] == "saved"
    assert entries[0]["lessons_learned"] == "Ask about on-call rotation earlier."


async def test_lessons_endpoint_omits_blank_notes(auth_client):
    client, _, _ = auth_client
    job = await _create_job(client)
    await client.post("/api/applications", json={"job_id": job["id"], "lessons_learned": ""})

    response = await client.get("/api/applications/lessons")

    assert response.json() == []


async def test_lessons_learned_can_be_added_on_update(auth_client):
    client, _, _ = auth_client
    job = await _create_job(client)
    application_id = (await client.post("/api/applications", json={"job_id": job["id"]})).json()[
        "id"
    ]

    updated = await client.put(
        f"/api/applications/{application_id}",
        json={"status": "rejected", "lessons_learned": "Prepare salary expectations upfront."},
    )

    assert updated.status_code == 200
    assert updated.json()["lessons_learned"] == "Prepare salary expectations upfront."

    entries = (await client.get("/api/applications/lessons")).json()
    assert len(entries) == 1
    assert entries[0]["status"] == "rejected"
    assert entries[0]["lessons_learned"] == "Prepare salary expectations upfront."


async def test_lessons_require_auth(client):
    assert (await client.get("/api/applications/lessons")).status_code == 401


async def test_applications_require_auth(client):
    assert (await client.get("/api/applications")).status_code == 401


async def test_get_application_detail_includes_job_description(auth_client):
    """The per-application workspace needs the job description and CV link."""
    client, _, _ = auth_client
    job = await _create_job(client)
    application_id = (await client.post("/api/applications", json={"job_id": job["id"]})).json()[
        "id"
    ]

    response = await client.get(f"/api/applications/{application_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == application_id
    assert body["job_title"] == "Data Engineer"
    assert body["job_company"] == "Acme"
    assert body["job_description"] == "ETL pipelines"
    assert body["cv_version"] is None


async def test_get_application_detail_returns_cv_version(auth_client):
    """A linked CV version is surfaced on the detail payload."""
    client, _, _ = auth_client
    job = await _create_job(client)
    cv = (await client.post("/api/cv", json={"structured_json": {"summary": "x"}})).json()
    application_id = (
        await client.post(
            "/api/applications", json={"job_id": job["id"], "cv_version": cv["id"]}
        )
    ).json()["id"]

    body = (await client.get(f"/api/applications/{application_id}")).json()

    assert body["cv_version"] == cv["id"]


async def test_get_application_detail_unknown_404(auth_client):
    client, _, _ = auth_client
    response = await client.get("/api/applications/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_get_application_detail_requires_auth(client):
    response = await client.get("/api/applications/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401


async def test_lessons_route_not_shadowed_by_detail_route(auth_client):
    """``/lessons`` is static and must win over ``/{application_id}``."""
    client, _, _ = auth_client
    assert (await client.get("/api/applications/lessons")).status_code == 200
