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

    created = await client.post(
        "/api/applications", json={"job_id": job["id"], "status": "saved"}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "saved"
    assert body["job_title"] == "Data Engineer"
    assert body["job_company"] == "Acme"

    updated = await client.put(
        f"/api/applications/{body['id']}", json={"status": "interview"}
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "interview"


async def test_list_applications_filter_by_status(auth_client):
    client, _, _ = auth_client
    job = await _create_job(client)
    application_id = (
        await client.post("/api/applications", json={"job_id": job["id"]})
    ).json()["id"]
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
    application_id = (
        await client.post("/api/applications", json={"job_id": job["id"]})
    ).json()["id"]
    await client.put(f"/api/applications/{application_id}", json={"status": "applied"})

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.entity_type == "application")
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].action == "updated"
    assert entries[0].changes["status"] == {"before": "saved", "after": "applied"}


async def test_applications_require_auth(client):
    assert (await client.get("/api/applications")).status_code == 401
