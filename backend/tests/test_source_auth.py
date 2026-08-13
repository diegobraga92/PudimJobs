"""Tests for per-source authentication (storing, masking, fetch context, SSRF)."""

import uuid

import pytest
from scrapers.utils import assert_safe_url
from sqlalchemy import select

from app.models import SourceAuth
from app.services.secrets import decrypt_secret
from app.services.source_auth import build_fetch_auth


async def _make_source(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/sources",
        json={"name": "Board", "url": "https://board.example/jobs", "type": "aggregator"},
    )
    return client, response.json()["id"]


async def test_set_auth_encrypts_and_masks_secret(auth_client):
    client, source_id = await _make_source(auth_client)
    response = await client.put(
        f"/api/sources/{source_id}/auth",
        json={"auth_type": "token", "token": "tok-abc123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["auth_type"] == "token"
    assert body["has_auth"] is True
    assert "tok-abc123" not in response.text


async def test_get_auth_returns_type_without_secret(auth_client):
    client, source_id = await _make_source(auth_client)
    await client.put(
        f"/api/sources/{source_id}/auth",
        json={"auth_type": "token", "token": "tok-987654"},
    )
    response = await client.get(f"/api/sources/{source_id}/auth")
    assert response.status_code == 200
    body = response.json()
    assert body["auth_type"] == "token"
    assert body["has_auth"] is True
    assert "tok-987654" not in response.text


async def test_clear_auth(auth_client):
    client, source_id = await _make_source(auth_client)
    await client.put(
        f"/api/sources/{source_id}/auth",
        json={"auth_type": "token", "token": "tok-abc"},
    )
    deleted = await client.delete(f"/api/sources/{source_id}/auth")
    assert deleted.status_code == 204
    response = await client.get(f"/api/sources/{source_id}/auth")
    assert response.json()["has_auth"] is False


async def test_set_auth_requires_secret(auth_client):
    client, source_id = await _make_source(auth_client)
    response = await client.put(
        f"/api/sources/{source_id}/auth",
        json={"auth_type": "token", "token": ""},
    )
    assert response.status_code == 400


async def test_cookies_auth_type_is_rejected(auth_client):
    """Cookie auth was removed (ToS/account-ban risk); it must be rejected."""
    client, source_id = await _make_source(auth_client)
    response = await client.put(
        f"/api/sources/{source_id}/auth",
        json={"auth_type": "cookies", "cookies": "session=abc"},
    )
    assert response.status_code == 422


async def test_api_key_auth_roundtrip(auth_client):
    client, source_id = await _make_source(auth_client)
    response = await client.put(
        f"/api/sources/{source_id}/auth",
        json={"auth_type": "api_key", "api_key": "sk-987654"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["auth_type"] == "api_key"
    assert body["has_auth"] is True
    assert "sk-987654" not in response.text

    detail = await client.get(f"/api/sources/{source_id}/auth")
    assert detail.json()["auth_type"] == "api_key"
    assert "sk-987654" not in detail.text


async def test_api_key_requires_value(auth_client):
    client, source_id = await _make_source(auth_client)
    response = await client.put(
        f"/api/sources/{source_id}/auth",
        json={"auth_type": "api_key", "api_key": ""},
    )
    assert response.status_code == 400


async def test_auth_isolation_between_users(auth_client, db_client, db_session):
    """User B must not read or modify user A's source auth."""
    client_a, source_id = await _make_source(auth_client)
    await client_a.put(
        f"/api/sources/{source_id}/auth",
        json={"auth_type": "token", "token": "tok-a-secret"},
    )
    from tests.helpers import create_user

    user_b = await create_user(db_session, email="other@example.com")
    login = await db_client.post(
        "/api/auth/login", json={"email": user_b.email, "password": "password123"}
    )
    db_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    assert (await db_client.get(f"/api/sources/{source_id}/auth")).status_code == 404
    assert (
        await db_client.put(
            f"/api/sources/{source_id}/auth",
            json={"auth_type": "token", "token": "tok-stolen"},
        )
    ).status_code == 404


async def test_credentials_stored_encrypted(auth_client, db_session):
    client, source_id = await _make_source(auth_client)
    await client.put(
        f"/api/sources/{source_id}/auth",
        json={"auth_type": "token", "token": "tok-plaintext-secret"},
    )
    record = (
        await db_session.execute(
            select(SourceAuth).where(SourceAuth.source_id == uuid.UUID(source_id))
        )
    ).scalar_one()
    assert "tok-plaintext-secret" not in record.credentials_encrypted
    assert decrypt_secret(record.credentials_encrypted) == "tok-plaintext-secret"


def test_build_fetch_auth_token_and_api_key():
    class _Record:
        def __init__(self, auth_type, secret):
            self.auth_type = auth_type
            self.credentials_encrypted = __import__(
                "app.services.secrets", fromlist=["encrypt_secret"]
            ).encrypt_secret(secret)

    token_auth = build_fetch_auth(_Record("token", "tok-123"))
    assert token_auth is not None
    assert token_auth.headers == {"Authorization": "Bearer tok-123"}

    api_key_auth = build_fetch_auth(_Record("api_key", "sk-456"))
    assert api_key_auth is not None
    assert api_key_auth.api_key == "sk-456"

    assert build_fetch_auth(None) is None


def test_assert_safe_url_blocks_unsafe_targets():
    with pytest.raises(ValueError):
        assert_safe_url("file:///etc/passwd")
    with pytest.raises(ValueError):
        assert_safe_url("ftp://example.com/file")
    with pytest.raises(ValueError):
        assert_safe_url("http://127.0.0.1:5432")
    with pytest.raises(ValueError):
        assert_safe_url("http://169.254.169.254/latest/meta-data")


def test_assert_safe_url_allowlist_bypass(monkeypatch):
    import scrapers.utils as utils_module

    monkeypatch.setattr(utils_module.settings, "scraper_allow_private_networks", True)
    # No exception for a loopback target when private networks are allowed.
    assert_safe_url("http://127.0.0.1:8000")
    monkeypatch.setattr(utils_module.settings, "scraper_allow_private_networks", False)
