from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api import fields, health
from app.core.error_handlers import register_error_handlers
from app.core.logger import get_logger, setup_logging
from app.core.settings import get_settings
from app.db.session import engine, ping_database
from app.middleware.request_id import request_id_middleware

logger = get_logger(__name__)

DESCRIPTION = """
REST API сільськогосподарських полів зі швидким пошуком полів за точкою (PostGIS + GIST).

**Швидкий сценарій демо** (усе виконується прямо тут, кнопкою *Try it out*):

1. `GET /api/fields/find-by-point?lon=30.5250&lat=50.4550` — точка з ТЗ, повертає
   кілька полів, що перекриваються.
2. `POST /api/fields` — приклади тіла: поле з ТЗ (201), «метелик» (400),
   менше 0.1 га (400), незамкнене кільце (422).
3. `GET /api/fields?crop=Пшениця&min_area=50&limit=5` — список з фільтрами.

Координати — у порядку GeoJSON `[lon, lat]`, SRID 4326.
Усі помилки — в єдиному форматі `{"error": {code, message, details, request_id}}`;
`request_id` також приходить у заголовку `X-Request-ID`.
"""

OPENAPI_TAGS = [
    {"name": "fields", "description": "Поля: створення, список, деталі, пошук за точкою"},
    {"name": "service", "description": "Службові ендпоінти"},
]


def operation_id(route: APIRoute) -> str:
    return route.name


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
    setup_logging(get_settings().log_level)

    app = FastAPI(
        title="Fields API",
        version="0.1.0",
        description=DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        generate_unique_id_function=operation_id,
        lifespan=lifespan,
    )
    app.include_router(fields.router)
    app.include_router(health.router)
    register_error_handlers(app)
    # Доданий останнім — найзовнішній серед користувацьких middleware
    app.middleware("http")(request_id_middleware)
    return app


app = create_app()
