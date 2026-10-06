"""Точка входу: `create_app()` збирає роутери, middleware, обробники помилок і lifespan."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.error_handlers import register_error_handlers
from app.core.logger import get_logger, setup_logging
from app.core.settings import get_settings
from app.db.session import engine, ping_database
from app.middleware.request_id import request_id_middleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Старт: одна перевірка PostgreSQL без ретраїв; зупинка: закриття пулу з'єднань.

    Чекати базу — задача healthcheck і `depends_on` у compose. Якщо база недоступна,
    процес падає одразу з зрозумілою помилкою (fail fast).
    """
    try:
        async with engine.connect() as conn:
            await ping_database(conn)
    except Exception as exc:
        # Traceback надрукує uvicorn ("Application startup failed"), тут — коротка причина
        logger.error("Database is unavailable at startup: %r", exc)
        raise
    logger.info("Application started, database is reachable")
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Створює FastAPI-застосунок."""
    setup_logging(get_settings().log_level)

    app = FastAPI(title="Fields API", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    register_error_handlers(app)
    # Доданий останнім — найзовнішній серед користувацьких middleware
    app.middleware("http")(request_id_middleware)
    return app


app = create_app()
