from __future__ import annotations

import asyncio
import os
import uuid

from sqlalchemy import select

from app.core.database import async_session_maker
from app.core.security import hash_password
from app.models.entities import User


async def seed_admin() -> None:
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@invoiceflow.io").lower().strip()
    admin_pass = os.environ.get("ADMIN_PASSWORD", "Admin@123456")

    async with async_session_maker() as session:
        stmt = select(User).where(User.email == admin_email)
        user = (await session.execute(stmt)).scalar_one_or_none()

        if user:
            user.password_hash = hash_password(admin_pass)
            user.role = "admin"
            user.is_active = True
            print(f"Updated existing admin user: {admin_email}")
        else:
            user = User(
                id=uuid.uuid4(),
                email=admin_email,
                password_hash=hash_password(admin_pass),
                role="admin",
                is_active=True,
            )
            session.add(user)
            print(f"Created initial admin user: {admin_email}")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_admin())
