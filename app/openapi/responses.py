"""Спільні `responses` для ендпоінтів: модель `ErrorResponse` і приклади на кожен код."""

from typing import Any

from fastapi.openapi.models import Example

from app.core.error_handlers import VALIDATION_ERROR_CODE, VALIDATION_ERROR_MESSAGE
from app.openapi.examples import DOMAIN_ERROR_EXAMPLES, VALIDATION_ERROR_DETAILS, error_body
from app.schemas.common import ErrorResponse

ERROR_DESCRIPTIONS = {
    400: "Invalid polygon or field area ≤ 0.1 ha (PostGIS checks)",
    404: "Field not found",
    422: "Request validation failed (Pydantic)",
    503: "Database is unavailable",
}


def error_responses(*status_codes: int, operation: str | None = None) -> dict[int | str, Any]:
    """`responses` для декоратора роуту: `error_responses(400, 422, operation="create_field")`.

    Приклади 4xx/5xx будуються з наших винятків; для 422 — приклад конкретного ендпоінта
    (`operation`). Явний 422 замінює стандартну схему FastAPI (`HTTPValidationError`).
    """
    responses: dict[int | str, Any] = {}
    for code in status_codes:
        if code == 422:
            if operation is None:
                raise ValueError("operation is required for the 422 example")
            examples = {
                VALIDATION_ERROR_CODE: Example(
                    summary=VALIDATION_ERROR_MESSAGE,
                    value=error_body(
                        VALIDATION_ERROR_CODE,
                        VALIDATION_ERROR_MESSAGE,
                        VALIDATION_ERROR_DETAILS[operation],
                    ),
                )
            }
        else:
            examples = DOMAIN_ERROR_EXAMPLES[code]
        responses[code] = {
            "model": ErrorResponse,
            "description": ERROR_DESCRIPTIONS[code],
            "content": {"application/json": {"examples": examples}},
        }
    return responses
