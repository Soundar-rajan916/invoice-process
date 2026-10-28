from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from mock_accounting.app import app as mock_accounting_app
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db_session
from app.main import app

settings.ENVIRONMENT = "test"

# SQLite in-memory test database for unit test suite
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
)

TestAsyncSessionMaker = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSessionMaker() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def dummy_page():
    from app.extraction.base import PageInput

    return PageInput(
        page_number=1,
        text="TAX INVOICE\nInvoice No: INV-100\nDate: 01/04/2026\nTotal: 1500.00",
        image_bytes=b"dummy_jpeg_bytes",
        is_digital=True,
        storage_key="pages/test/1.jpg",
        original_filename="inv.pdf",
    )


@pytest.fixture
async def mock_accounting_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=mock_accounting_app)
    async with AsyncClient(transport=transport, base_url="http://mock-accounting") as c:
        yield c


@pytest.fixture
async def reviewer_user(db_session: AsyncSession):
    import uuid

    from app.core.security import hash_password
    from app.models.entities import User

    user = User(
        id=uuid.uuid4(),
        email="reviewer@test.com",
        password_hash=hash_password("ReviewerPass123"),
        role="reviewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def admin_user(db_session: AsyncSession):
    import uuid

    from app.core.security import hash_password
    from app.models.entities import User

    user = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        password_hash=hash_password("AdminPass123"),
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def reviewer_client(
    db_session: AsyncSession, reviewer_user
) -> AsyncGenerator[AsyncClient, None]:
    from app.core.security import create_access_token

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    token = create_access_token(reviewer_user.id, reviewer_user.role)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", cookies={"access_token": token}
    ) as c:
        yield c


@pytest.fixture
async def admin_client(db_session: AsyncSession, admin_user) -> AsyncGenerator[AsyncClient, None]:
    from app.core.security import create_access_token

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    token = create_access_token(admin_user.id, admin_user.role)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", cookies={"access_token": token}
    ) as c:
        yield c
