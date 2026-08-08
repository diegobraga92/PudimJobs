"""Authentication and authorisation helpers (JWT + bcrypt)."""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt (salt is embedded in the hash)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Compare a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """Issue a signed JWT access token."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency that resolves and returns the authenticated user."""
    if credentials is None:
        raise _unauthorized()

    try:
        payload = jwt.decode(
            credentials.credentials, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized() from exc

    subject = payload.get("sub")
    if subject is None:
        raise _unauthorized()
    try:
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise _unauthorized() from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise _unauthorized()
    return user
