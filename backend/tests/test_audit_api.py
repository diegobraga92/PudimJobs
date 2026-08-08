"""Tests for the audit log investigation API."""

from app.models import AuditLog
from tests.helpers import create_user


async def _make_admin(db_client, db_session):
    admin = await create_user(db_session, email="admin@audit.dev", role="admin")
    response = await db_client.post(
        "/api/auth/login", json={"email": admin.email, "password": "password123"}
    )
    db_client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return admin


async def test_audit_requires_admin(auth_client):
    client, _, _ = auth_client
    assert (await client.get("/api/admin/audit")).status_code == 403


async def test_audit_list_and_filters(db_client, db_session):
    admin = await _make_admin(db_client, db_session)
    db_session.add_all(
        [
            AuditLog(
                user_id=admin.id,
                action="created",
                entity_type="master_cv",
                changes={"version": 1},
            ),
            AuditLog(
                user_id=admin.id,
                action="updated",
                entity_type="application",
                changes={"status": {"before": "saved", "after": "interview"}},
            ),
        ]
    )
    await db_session.commit()

    response = await db_client.get("/api/admin/audit")
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 2
    assert all(entry["email"] == "admin@audit.dev" for entry in entries)
    assert {entry["action"] for entry in entries} == {"created", "updated"}

    filtered = await db_client.get("/api/admin/audit", params={"action": "created"})
    assert len(filtered.json()) == 1

    type_filtered = await db_client.get(
        "/api/admin/audit", params={"entity_type": "application"}
    )
    assert len(type_filtered.json()) == 1
    assert type_filtered.json()[0]["changes"]["status"]["after"] == "interview"


async def test_audit_actions_lists_facets(db_client, db_session):
    admin = await _make_admin(db_client, db_session)
    db_session.add(
        AuditLog(user_id=admin.id, action="replay", entity_type="reprocessing")
    )
    await db_session.commit()

    response = await db_client.get("/api/admin/audit/actions")
    assert response.status_code == 200
    body = response.json()
    assert "reprocessing" in body["entity_types"]
    assert "replay" in body["actions"]
