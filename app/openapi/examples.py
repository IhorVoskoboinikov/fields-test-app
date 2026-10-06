"""Приклади для Swagger: сценарії тіла POST і тіла помилок.

Приклади успішних відповідей описані в самих Pydantic-схемах (`Field(examples=...)`).
"""

from typing import Any
from uuid import UUID

from fastapi.openapi.models import Example

from app.core.exceptions import (
    AppError,
    DatabaseUnavailableError,
    FieldAreaTooSmallError,
    FieldNotFoundError,
    InvalidGeometryError,
)

REQUEST_ID = "3f2a9c1e-7d4b-4c1a-9a0e-2b5f6c7d8e9f"
FIELD_ID = "8c7ff87a-cabd-48fa-bf7c-b47f94edc665"

# Поле з прикладу ТЗ
TZ_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [30.5234, 50.4501],
            [30.5334, 50.4501],
            [30.5334, 50.4601],
            [30.5234, 50.4601],
            [30.5234, 50.4501],
        ]
    ],
}
TZ_FIELD = {
    "name": "Поле №1 - Пшениця",
    "geometry": TZ_POLYGON,
    "crop": "Пшениця",
    "owner": "Іванов І.І.",
}

FIELD_CREATE_EXAMPLES: dict[str, Example] = {
    "tz": Example(
        summary="Поле з ТЗ → 201",
        description="Тіло з прикладу ТЗ. Площа на еліпсоїді — 79.00 га.",
        value=TZ_FIELD,
    ),
    "bowtie": Example(
        summary="Самоперетин («метелик») → 400",
        description="Сторони перетинаються, як у вісімці: `ST_IsValid` = false.",
        value={
            **TZ_FIELD,
            "name": "Метелик",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[30.50, 50.40], [30.52, 50.42], [30.52, 50.40], [30.50, 50.42], [30.50, 50.40]]
                ],
            },
        },
    ),
    "tiny": Example(
        summary="Менше 0.1 га → 400",
        description="Квадрат приблизно 7 × 11 м — близько 0.008 га.",
        value={
            **TZ_FIELD,
            "name": "Замале поле",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [30.5000, 50.4000],
                        [30.5001, 50.4000],
                        [30.5001, 50.4001],
                        [30.5000, 50.4001],
                        [30.5000, 50.4000],
                    ]
                ],
            },
        },
    ),
    "open_ring": Example(
        summary="Незамкнене кільце → 422",
        description="Перша точка не дорівнює останній — відхиляє Pydantic.",
        value={
            **TZ_FIELD,
            "name": "Незамкнене",
            "geometry": {"type": "Polygon", "coordinates": [TZ_POLYGON["coordinates"][0][:-1]]},
        },
    ),
}


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    """Тіло помилки в єдиному форматі (як у `error_response`: без `details`, якщо їх немає)."""
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    error["request_id"] = REQUEST_ID
    return {"error": error}


def domain_error_examples(*errors: AppError) -> dict[int, dict[str, Example]]:
    """Приклади з самих винятків (статус → {code: приклад}): code, message і details
    беруться з класів помилок, тож документація не розійдеться з кодом."""
    examples: dict[int, dict[str, Example]] = {}
    for error in errors:
        examples.setdefault(error.status_code, {})[error.code] = Example(
            summary=error.message, value=error_body(error.code, error.message, error.details)
        )
    return examples


# details — як у реальних відповідях на приклади тіла POST вище («метелик»,
# «менше 0.1 га») і на запит невідомого id
DOMAIN_ERROR_EXAMPLES = domain_error_examples(
    InvalidGeometryError("Self-intersection[30.51 50.41]"),
    FieldAreaTooSmallError(0.0079),
    FieldNotFoundError(UUID(FIELD_ID)),
    DatabaseUnavailableError(),
)

# 422 у кожного ендпоінта свій: `details` рівно такі, як повертає застосунок
# (відповідність перевіряє tests/integration/api/test_openapi_examples.py).
VALIDATION_ERROR_DETAILS: dict[str, list[dict[str, Any]]] = {
    # POST /api/fields з прикладом «Незамкнене кільце»
    "create_field": [
        {
            "loc": ["body", "geometry", "coordinates"],
            "msg": "Value error, ring 0 is not closed: first and last positions must be equal",
            "type": "value_error",
        }
    ],
    # GET /api/fields?crop=
    "list_fields": [
        {
            "loc": ["query", "crop"],
            "msg": "String should have at least 1 character",
            "type": "string_too_short",
        }
    ],
    # GET /api/fields/find-by-point?lon=30.5&lat=100
    "find_fields_by_point": [
        {
            "loc": ["query", "lat"],
            "msg": "Input should be less than or equal to 90",
            "type": "less_than_equal",
        }
    ],
    # GET /api/fields/abc
    "get_field": [
        {
            "loc": ["path", "field_id"],
            "msg": (
                "Input should be a valid UUID, invalid length: "
                "expected length 32 for simple format, found 3"
            ),
            "type": "uuid_parsing",
        }
    ],
}
