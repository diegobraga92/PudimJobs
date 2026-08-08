"""Tests for JWT authentication."""

from app.auth import create_access_token, hash_password, verify_password
from tests.helpers import create_user


async def test_password_hashing_roundtrip():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong-password", hashed)


async def test_create_access_token_has_jwt_structure():
    token = create_access_token("11111111-1111-1111-1111-111111111111", "admin")
    assert isinstance(token, str) and token.count(".") == 2


async def test_login_success(auth_client):
    _, _, token = auth_client
    assert token


async def test_login_wrong_password(db_client, db_session):
    await create_user(db_session)
    response = await db_client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


async def test_me_requires_token(client):
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


async def test_me_with_token(auth_client):
    client, user, _ = auth_client
    response = await client.get("/api/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == user.email
    assert body["role"] == "user"
