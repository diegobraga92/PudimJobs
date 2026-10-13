"""Tests for the interview-prep task API."""

from sqlalchemy import select

from app.models.audit_log import AuditLog
from tests.helpers import create_user


async def _create_job(client, title="Data Engineer", company="Acme") -> dict:
    response = await client.post(
        "/api/jobs",
        json={"title": title, "company": company, "description": "ETL pipelines"},
    )
    assert response.status_code == 201
    return response.json()


async def _create_task(client, **overrides) -> dict:
    payload = {"title": "Revise SQL window functions", **overrides}
    response = await client.post("/api/prep-tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_and_list_prep_tasks_with_job_context(auth_client):
    client, _, _ = auth_client
    job = await _create_job(client)

    created = await _create_task(
        client,
        title="Re-read the job description",
        category="research",
        due_date="2026-11-01",
        notes="Focus on the data platform section",
        job_id=job["id"],
    )

    assert created["status"] == "pending"
    assert created["category"] == "research"
    assert created["due_date"] == "2026-11-01"
    assert created["job_title"] == "Data Engineer"
    assert created["job_company"] == "Acme"

    listed = await client.get("/api/prep-tasks")
    assert listed.status_code == 200
    assert [task["id"] for task in listed.json()] == [created["id"]]


async def test_get_single_prep_task(auth_client):
    client, _, _ = auth_client
    created = await _create_task(client)

    fetched = await client.get(f"/api/prep-tasks/{created['id']}")

    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Revise SQL window functions"
    assert fetched.json()["job_title"] is None


async def test_list_orders_unfinished_and_dated_tasks_first(auth_client):
    client, _, _ = auth_client
    done = await _create_task(client, title="Done", status="done", due_date="2026-01-01")
    later = await _create_task(client, title="Later", due_date="2027-01-01")
    sooner = await _create_task(client, title="Sooner", due_date="2026-06-01")
    undated = await _create_task(client, title="Undated")

    listed = (await client.get("/api/prep-tasks")).json()

    assert [task["title"] for task in listed] == ["Sooner", "Later", "Undated", "Done"]
    assert listed[0]["id"] == sooner["id"]
    assert listed[1]["id"] == later["id"]
    assert listed[2]["id"] == undated["id"]
    assert listed[3]["id"] == done["id"]


async def test_list_filters_by_status_and_job(auth_client):
    client, _, _ = auth_client
    first_job = await _create_job(client, title="Data Engineer")
    second_job = await _create_job(client, title="Platform Engineer")
    await _create_task(client, title="Mock interview", job_id=first_job["id"])
    await _create_task(client, title="Read docs", job_id=second_job["id"], status="done")

    done = (await client.get("/api/prep-tasks", params={"status_filter": "done"})).json()
    assert [task["title"] for task in done] == ["Read docs"]

    scoped = (await client.get("/api/prep-tasks", params={"job_id": first_job["id"]})).json()
    assert [task["title"] for task in scoped] == ["Mock interview"]


async def test_update_prep_task_is_audited(auth_client, db_session):
    client, user, _ = auth_client
    job = await _create_job(client)
    created = await _create_task(client, title="Practice system design", job_id=job["id"])

    updated = await client.put(
        f"/api/prep-tasks/{created['id']}",
        json={"status": "in_progress", "due_date": "2026-12-24", "job_id": None},
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["status"] == "in_progress"
    assert body["due_date"] == "2026-12-24"
    assert body["job_id"] is None
    assert body["job_title"] is None

    result = await db_session.execute(select(AuditLog).where(AuditLog.entity_type == "prep_task"))
    entries = result.scalars().all()
    assert [entry.action for entry in entries] == ["updated"]
    assert entries[0].changes["status"] == {"before": "pending", "after": "in_progress"}
    assert entries[0].changes["job_id"]["after"] == "None"
    assert entries[0].user_id == user.id


async def test_update_without_changes_writes_no_audit_entry(auth_client, db_session):
    client, _, _ = auth_client
    created = await _create_task(client, category="technical")

    response = await client.put(f"/api/prep-tasks/{created['id']}", json={"category": "technical"})

    assert response.status_code == 200
    result = await db_session.execute(select(AuditLog).where(AuditLog.entity_type == "prep_task"))
    assert result.scalars().all() == []


async def test_delete_prep_task(auth_client, db_session):
    client, _, _ = auth_client
    created = await _create_task(client)

    deleted = await client.delete(f"/api/prep-tasks/{created['id']}")

    assert deleted.status_code == 204
    assert (await client.get(f"/api/prep-tasks/{created['id']}")).status_code == 404
    result = await db_session.execute(select(AuditLog).where(AuditLog.entity_type == "prep_task"))
    entries = result.scalars().all()
    assert [entry.action for entry in entries] == ["deleted"]
    assert entries[0].entity_id == str(created["id"])


async def test_create_rejects_unknown_job_or_application(auth_client):
    client, _, _ = auth_client
    unknown = "00000000-0000-0000-0000-000000000000"

    job_response = await client.post("/api/prep-tasks", json={"title": "Task", "job_id": unknown})
    assert job_response.status_code == 404
    assert job_response.json()["detail"] == "Job not found"

    application_response = await client.post(
        "/api/prep-tasks", json={"title": "Task", "application_id": unknown}
    )
    assert application_response.status_code == 404
    assert application_response.json()["detail"] == "Application not found"


async def test_create_validates_title_and_category(auth_client):
    client, _, _ = auth_client

    empty_title = await client.post("/api/prep-tasks", json={"title": ""})
    assert empty_title.status_code == 422

    bad_category = await client.post(
        "/api/prep-tasks", json={"title": "Task", "category": "not-a-category"}
    )
    assert bad_category.status_code == 422


async def test_tasks_are_scoped_to_their_owner(auth_client, db_session):
    client, _, _ = auth_client
    created = await _create_task(client, title="Only mine")

    other = await create_user(db_session, email="other@example.com")
    login = await client.post(
        "/api/auth/login", json={"email": other.email, "password": "password123"}
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    assert (await client.get("/api/prep-tasks")).json() == []
    assert (await client.get(f"/api/prep-tasks/{created['id']}")).status_code == 404
    update = await client.put(f"/api/prep-tasks/{created['id']}", json={"status": "done"})
    assert update.status_code == 404
    assert (await client.delete(f"/api/prep-tasks/{created['id']}")).status_code == 404


async def test_prep_tasks_require_auth(client):
    assert (await client.get("/api/prep-tasks")).status_code == 401
