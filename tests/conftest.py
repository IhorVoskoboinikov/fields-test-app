"""Інфраструктурні фікстури: PostGIS у контейнері, міграції, застосунок і HTTP-клієнт.

PostGIS справжній, бо `ST_Intersects`, `ST_IsValid` і `ST_Area(geography)` не
перевірити на SQLite чи моках: тест перевіряв би фейк, а не наш код.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer

from app.dependencies.db import get_session
from app.main import create_app
from tests.helpers import TZ_FIELD

POSTGIS_IMAGE = "postgis/postgis:16-3.4"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

CreateField = Callable[..., Awaitable[dict[str, Any]]]


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Піднімає PostGIS у контейнері на всю сесію тестів і віддає async-URL."""
    with PostgresContainer(POSTGIS_IMAGE, driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def migrated_db(postgres_url: str) -> str:
    """Схема створюється міграціями (а не create_all) — тести заодно перевіряють міграції.

    Фікстура синхронна: async env.py викликає asyncio.run(), з async-фікстури це впало б.
    """
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(config, "head")
    return postgres_url


@pytest.fixture(scope="session")
async def engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    """Async-engine тестової бази на всю сесію."""
    engine = create_async_engine(migrated_db)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_db(engine: AsyncEngine) -> AsyncIterator[None]:
    """Ізоляція тестів: після кожного тесту таблиця очищається.

    TRUNCATE, а не savepoint: сервіс сам відкриває `session.begin()`.
    """
    yield
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE fields"))


@pytest.fixture
def app(engine: AsyncEngine) -> FastAPI:
    """Застосунок із сесією на тестову базу через `dependency_overrides`."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """HTTP-клієнт, що викликає застосунок напряму, без мережі."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def create_field(client: AsyncClient) -> CreateField:
    """Фабрика: створює поле через POST і повертає JSON відповіді."""

    async def factory(**overrides: Any) -> dict[str, Any]:
        response = await client.post("/api/fields", json={**TZ_FIELD, **overrides})
        assert response.status_code == 201, response.text
        return response.json()

    return factory
