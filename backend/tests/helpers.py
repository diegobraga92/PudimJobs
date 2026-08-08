"""Test helper functions."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.models import User


async def create_user(
    session: AsyncSession,
    email: str = "user@example.com",
    password: str = "password123",
    role: str = "user",
) -> User:
    """Create and persist a user, returning the ORM instance."""
    user = User(email=email, password_hash=hash_password(password), role=role)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
