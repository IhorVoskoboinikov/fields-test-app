from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import get_settings


def create_engine(database_url: str | None = None) -> AsyncEngine:
    return create_async_engine(database_url or get_settings().database_url, pool_pre_ping=True)


engine = create_engine()
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def ping_database(executor: AsyncConnection | AsyncSession) -> None:
    """Перевіряє, що база відповідає (`SELECT 1`). Спільний код для старту застосунку і /health."""
    await executor.execute(text("SELECT 1"))
