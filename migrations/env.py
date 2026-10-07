import asyncio
from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.db.models  # noqa: F401 — реєструє моделі в Base.metadata
from app.core.settings import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    # Не вимикати логери, створені до міграцій (наприклад, у тестах після імпорту застосунку)
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def get_url() -> str:
    """URL бази: явно переданий у Config (тести) або з налаштувань застосунку."""
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Одне правило: не чіпати таблиці, яких немає в наших моделях.

    Покриває `spatial_ref_sys` і все, що створює образ PostGIS;
    інакше autogenerate згенерував би для них DROP TABLE.
    """
    return not (type_ == "table" and reflected and compare_to is None)


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        include_object=include_object,
        # Хелпери GeoAlchemy2: коректні операції з геометричними колонками
        # й індексами та `import geoalchemy2` у файлі міграції
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(url=get_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(get_url(), poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
