"""Службовий ендпоінт /health: застосунок живий і база відповідає. Його ж використовує Docker."""

from fastapi import APIRouter

from app.core.exceptions import DatabaseUnavailableError
from app.core.logger import get_logger
from app.db.session import ping_database
from app.dependencies.db import SessionDep
from app.openapi.responses import error_responses
from app.schemas.common import HealthResponse

router = APIRouter(tags=["service"])
logger = get_logger(__name__)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Перевірка стану",
    description="200 — застосунок працює і PostgreSQL відповідає; 503 — база недоступна.",
    responses=error_responses(503),
)
async def health(session: SessionDep) -> HealthResponse:
    """Виконує `SELECT 1`; будь-яка помилка з'єднання → 503."""
    try:
        await ping_database(session)
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        raise DatabaseUnavailableError from exc
    return HealthResponse()
