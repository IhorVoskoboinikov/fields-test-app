"""Async-engine і фабрика сесій. Одна `AsyncSession` на HTTP-запит."""

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.settings import get_settings


def create_engine(database_url: str | None = None) -> AsyncEngine:
    """Створює async-engine з пулом з'єднань (з'єднання не відкривається на кожен запит)."""
    return create_async_engine(database_url or get_settings().database_url, pool_pre_ping=True)


engine = create_engine()
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
