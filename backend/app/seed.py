"""Idempotent seed script.

Creates the development admin user. Run with::

    python -m app.seed

Credentials (dev only):
    admin@pudimjobs.dev / admin123
"""

import asyncio

from sqlalchemy import select

from app.auth import hash_password
from app.database import async_session_factory
from app.models.user import User

ADMIN_EMAIL = "admin@pudimjobs.dev"
ADMIN_PASSWORD = "admin123"


async def seed() -> None:
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.email == ADMIN_EMAIL))
        if result.scalar_one_or_none() is not None:
            print(f"Admin user already exists ({ADMIN_EMAIL})")
            return
        session.add(
            User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                role="admin",
            )
        )
        await session.commit()
        print(f"Seeded admin user: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
