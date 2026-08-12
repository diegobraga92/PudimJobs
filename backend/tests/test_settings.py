"""Tests for the admin LLM-config settings API."""

from app.models import AuditLog
from tests.helpers import create_user


async def _login(db_client, email: str) -> None:
    response = await db_client.post(
        "/api/auth/login", json={"email": email, "password": "password123"}
    )
    db_client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"


async def _make_admin(db_client, db_session):
    user = await create_user(db_session, email="admin@example.com", role="admin")
    await _login(db_client, user.email)
    return user


async def test_llm_config_rejects_regular_user(auth_client):
    client, _, _ = auth_client
    assert (await client.get("/api/admin/settings/llm")).status_code == 403
    assert (await client.put("/api/admin/settings/llm", json={})).status_code == 403


async def test_llm_config_get_returns_defaults(db_client, db_session):
    await _make_admin(db_client, db_session)
    response = await db_client.get("/api/admin/settings/llm")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["model"] == "gpt-4o-mini"
    assert body["api_key_masked"] is None


async def test_llm_config_update_encrypts_and_masks_key(db_client, db_session):
    await _make_admin(db_client, db_session)
    response = await db_client.put(
        "/api/admin/settings/llm",
        json={
            "enabled": True,
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "api_key": "sk-test-1234567890abcdef",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["api_key_masked"] == "sk-t…cdef"
    assert "sk-test-1234567890abcdef" not in response.text


async def test_llm_config_never_leaks_key_in_get(db_client, db_session):
    await _make_admin(db_client, db_session)
    await db_client.put(
        "/api/admin/settings/llm",
        json={
            "enabled": True,
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "api_key": "sk-leak-check-1234",
        },
    )
    response = await db_client.get("/api/admin/settings/llm")
    assert response.status_code == 200
    assert "sk-leak-check-1234" not in response.text
    assert "sk-l…1234" in response.text


async def test_llm_config_update_writes_audit_without_secret(db_client, db_session):
    admin = await _make_admin(db_client, db_session)
    await db_client.put(
        "/api/admin/settings/llm",
        json={
            "enabled": True,
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "api_key": "sk-audit-9999",
        },
    )
    entries = (await db_session.execute(
        __import__("sqlalchemy").select(AuditLog)
    )).scalars().all()
    matching = [e for e in entries if e.entity_type == "llm_config" and e.user_id == admin.id]
    assert matching
    assert "sk-audit-9999" not in str(matching[0].changes)
