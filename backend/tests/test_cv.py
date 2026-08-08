"""Tests for the master CV API (versioning + audit)."""

from sqlalchemy import select

from app.models.audit_log import AuditLog

CV_PAYLOAD = {
    "summary": "Backend engineer",
    "experience": [
        {
            "company": "Acme",
            "title": "Engineer",
            "start_date": "2020-01",
            "bullets": ["Built async pipelines"],
        }
    ],
    "education": [{"institution": "MIT", "degree": "BSc Computer Science"}],
    "skills": ["python", "fastapi"],
    "projects": [{"name": "PudimJobs", "description": "Job application tracker"}],
}


async def test_create_cv_versions_and_current(auth_client):
    client, _, _ = auth_client

    first = await client.post("/api/cv", json={"structured_json": CV_PAYLOAD})
    assert first.status_code == 201
    assert first.json()["version"] == 1
    assert first.json()["is_current"] is True
    assert first.json()["label"] == "CV v1"

    second = await client.post(
        "/api/cv", json={"structured_json": CV_PAYLOAD, "label": "Tailored"}
    )
    assert second.status_code == 201
    assert second.json()["version"] == 2
    assert second.json()["label"] == "Tailored"
    assert second.json()["is_current"] is True

    current = await client.get("/api/cv/current")
    assert current.json()["version"] == 2

    versions = await client.get("/api/cv")
    assert [v["version"] for v in versions.json()] == [2, 1]
    assert versions.json()[1]["is_current"] is False


async def test_cv_creation_writes_audit_log(auth_client, db_session):
    client, user, _ = auth_client
    await client.post("/api/cv", json={"structured_json": CV_PAYLOAD})

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.user_id == user.id)
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].entity_type == "master_cv"
    assert entries[0].action == "created"
    assert entries[0].changes == {"version": 1}


async def test_cv_requires_auth(client):
    assert (await client.get("/api/cv")).status_code == 401
