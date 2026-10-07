"""Спільні `responses` для ендпоінтів: модель `ErrorResponse` і приклади на кожен код."""

from typing import Any

from app.openapi.examples import DOMAIN_ERROR_EXAMPLES
from app.schemas.common import ErrorResponse

ERROR_DESCRIPTIONS = {
    400: "Invalid polygon or field area ≤ 0.1 ha (PostGIS checks)",
    404: "Field not found",
    422: "Request validation failed (Pydantic)",
    503: "Database is unavailable",
}


def error_responses(*status_codes: int) -> dict[int | str, Any]:
    """`responses` для декоратора роуту: `error_responses(400, 422)`.

    Приклади 400/404/503 будуються з наших винятків; 422 описаний лише моделлю
    `ErrorResponse` (явний 422 замінює стандартну схему FastAPI `HTTPValidationError`).
    """
    responses: dict[int | str, Any] = {}
    for code in status_codes:
        response: dict[str, Any] = {"model": ErrorResponse, "description": ERROR_DESCRIPTIONS[code]}
        if code in DOMAIN_ERROR_EXAMPLES:
            response["content"] = {"application/json": {"examples": DOMAIN_ERROR_EXAMPLES[code]}}
        responses[code] = response
    return responses
