"""Спільні `responses` для ендпоінтів: модель `ErrorResponse` і приклади на кожен код."""

from typing import Any

from app.openapi.examples import ERROR_EXAMPLES
from app.schemas.common import ErrorResponse

ERROR_DESCRIPTIONS = {
    400: "Геометрія невалідна (PostGIS)",
    404: "Не знайдено",
    422: "Помилка валідації запиту (Pydantic)",
    503: "Сервіс тимчасово недоступний",
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """`responses` для декоратора роуту: `error_responses(400, 422)`.

    Явний 422 замінює стандартну схему FastAPI (`HTTPValidationError`) нашим форматом.
    """
    return {
        code: {
            "model": ErrorResponse,
            "description": ERROR_DESCRIPTIONS[code],
            "content": {"application/json": {"examples": ERROR_EXAMPLES[code]}},
        }
        for code in status_codes
    }


def success_example(example: dict[str, Any]) -> dict[str, Any]:
    """Приклад успішної відповіді (модель береться з `response_model` роуту)."""
    return {"content": {"application/json": {"example": example}}}
