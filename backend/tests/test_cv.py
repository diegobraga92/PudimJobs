"""Tests for the master CV API (versioning + audit)."""

import uuid

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.generated_cv import GeneratedCV
from tests.helpers import create_user

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

    second = await client.post("/api/cv", json={"structured_json": CV_PAYLOAD, "label": "Tailored"})
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

    result = await db_session.execute(select(AuditLog).where(AuditLog.user_id == user.id))
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].entity_type == "master_cv"
    assert entries[0].action == "created"
    assert entries[0].changes == {"version": 1}


async def test_export_cv_pdf(auth_client):
    client, _, _ = auth_client
    response = await client.post("/api/cv/pdf", json=CV_PAYLOAD)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


async def test_cv_requires_auth(client):
    assert (await client.get("/api/cv")).status_code == 401


async def test_delete_current_cv_promotes_next_version(auth_client):
    client, _, _ = auth_client
    first = (await client.post("/api/cv", json={"structured_json": CV_PAYLOAD})).json()
    second = (
        await client.post("/api/cv", json={"structured_json": CV_PAYLOAD, "label": "Tailored"})
    ).json()

    response = await client.delete(f"/api/cv/{second['id']}")
    assert response.status_code == 204

    current = await client.get("/api/cv/current")
    assert current.status_code == 200
    assert current.json()["id"] == first["id"]
    assert current.json()["is_current"] is True

    versions = await client.get("/api/cv")
    assert len(versions.json()) == 1


async def test_delete_non_current_cv_keeps_current(auth_client):
    client, _, _ = auth_client
    first = (await client.post("/api/cv", json={"structured_json": CV_PAYLOAD})).json()
    second = (
        await client.post("/api/cv", json={"structured_json": CV_PAYLOAD, "label": "Tailored"})
    ).json()

    response = await client.delete(f"/api/cv/{first['id']}")
    assert response.status_code == 204

    current = await client.get("/api/cv/current")
    assert current.status_code == 200
    assert current.json()["id"] == second["id"]


async def test_delete_last_cv_leaves_no_current(auth_client):
    client, _, _ = auth_client
    created = (await client.post("/api/cv", json={"structured_json": CV_PAYLOAD})).json()

    response = await client.delete(f"/api/cv/{created['id']}")
    assert response.status_code == 204

    assert (await client.get("/api/cv/current")).status_code == 404
    assert (await client.get("/api/cv")).json() == []


async def test_delete_cv_version_unknown_404(auth_client):
    client, _, _ = auth_client
    response = await client.delete("/api/cv/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_delete_generated_cv(auth_client, db_session):
    client, user, _ = auth_client
    job = (await client.post("/api/jobs", json={"title": "Engineer", "company": "Acme"})).json()
    generated = GeneratedCV(
        user_id=user.id,
        job_id=uuid.UUID(job["id"]),
        pdf=b"%PDF-1.4 fake",
    )
    db_session.add(generated)
    await db_session.commit()
    await db_session.refresh(generated)

    listed = await client.get("/api/cv/generated")
    assert len(listed.json()) == 1

    response = await client.delete(f"/api/cv/generated/{generated.id}")
    assert response.status_code == 204

    assert (await client.get("/api/cv/generated")).json() == []


async def test_delete_generated_cv_unknown_404(auth_client):
    client, _, _ = auth_client
    response = await client.delete("/api/cv/generated/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_list_generated_filters_by_job(auth_client, db_session):
    """``?job_id=`` scopes the list — this powers the application CV panel."""
    client, user, _ = auth_client
    job_a = (await client.post("/api/jobs", json={"title": "A", "company": "Acme"})).json()
    job_b = (await client.post("/api/jobs", json={"title": "B", "company": "Acme"})).json()

    db_session.add_all(
        [
            GeneratedCV(user_id=user.id, job_id=uuid.UUID(job_a["id"]), pdf=b"%PDF-1.4 a"),
            GeneratedCV(user_id=user.id, job_id=uuid.UUID(job_b["id"]), pdf=b"%PDF-1.4 b"),
        ]
    )
    await db_session.commit()

    unfiltered = await client.get("/api/cv/generated")
    assert len(unfiltered.json()) == 2
    assert {row["variant"] for row in unfiltered.json()} == {"rule"}

    scoped = await client.get("/api/cv/generated", params={"job_id": job_a["id"]})
    assert [row["job_id"] for row in scoped.json()] == [job_a["id"]]


async def test_update_generated_cv_edits_in_place(auth_client, db_session):
    """Editing a tailored CV re-renders its PDF and clears the stale ATS cache."""
    client, user, _ = auth_client
    job = (await client.post("/api/jobs", json={"title": "Engineer", "company": "Acme"})).json()
    generated = GeneratedCV(
        user_id=user.id,
        job_id=uuid.UUID(job["id"]),
        pdf=b"%PDF-1.4 old",
        structured_json={"summary": "old"},
        ats_score=42,
        ats_report={"score": 42},
    )
    db_session.add(generated)
    await db_session.commit()
    await db_session.refresh(generated)

    response = await client.put(
        f"/api/cv/generated/{generated.id}",
        json={"structured_json": {**CV_PAYLOAD, "summary": "Rewritten summary"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["structured_json"]["summary"] == "Rewritten summary"
    assert body["variant"] == "rule"
    assert body["ats_score"] is None
    assert body["ats_report"] is None
    assert body["job_title"] == "Engineer"

    await db_session.refresh(generated)
    assert generated.pdf[:4] == b"%PDF"

    entries = (
        (await db_session.execute(select(AuditLog).where(AuditLog.entity_type == "generated_cv")))
        .scalars()
        .all()
    )
    assert [entry.action for entry in entries] == ["updated"]


async def test_update_generated_cv_rejects_another_users_cv(auth_client, db_session):
    client, _, _ = auth_client
    other = await create_user(db_session, email="generated-owner@example.com")
    generated = GeneratedCV(user_id=other.id, pdf=b"%PDF-1.4 stub")
    db_session.add(generated)
    await db_session.commit()
    await db_session.refresh(generated)

    response = await client.put(
        f"/api/cv/generated/{generated.id}", json={"structured_json": CV_PAYLOAD}
    )

    assert response.status_code == 404


async def test_update_generated_cv_unknown_404(auth_client):
    client, _, _ = auth_client
    response = await client.put(
        "/api/cv/generated/00000000-0000-0000-0000-000000000000",
        json={"structured_json": CV_PAYLOAD},
    )
    assert response.status_code == 404
