"""Приклади тіл запитів і відповідей для Swagger. Усі сценарії демо — прямо з /docs."""

from typing import Any

from fastapi.openapi.models import Example

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

FIELD_READ_EXAMPLE: dict[str, Any] = {
    "id": FIELD_ID,
    **{key: TZ_FIELD[key] for key in ("name", "geometry")},
    "area_ha": 79.0,
    "crop": "Пшениця",
    "owner": "Іванов І.І.",
    "created_at": "2026-10-06T07:04:06Z",
}

FIELD_LIST_EXAMPLE: dict[str, Any] = {
    "total": 2001,
    "fields": [
        {
            "id": FIELD_ID,
            "name": "Поле №1 - Пшениця",
            "area_ha": 79.0,
            "crop": "Пшениця",
            "owner": "Іванов І.І.",
        }
    ],
}

FIND_BY_POINT_EXAMPLE: dict[str, Any] = {
    "query_point": {"lon": 30.525, "lat": 50.455},
    "fields": [
        {
            "id": FIELD_ID,
            "name": "Поле №1 - Пшениця",
            "area_ha": 79.0,
            "crop": "Пшениця",
            "owner": "Іванов І.І.",
            "distance_to_center_m": 241.7,
        }
    ],
    "query_time_ms": 1.35,
}


def error_example(code: str, message: str, details: Any = None) -> dict[str, Any]:
    """Тіло помилки в єдиному форматі для прикладів."""
    return {
        "error": {"code": code, "message": message, "details": details, "request_id": REQUEST_ID}
    }


ERROR_EXAMPLES: dict[int, dict[str, Example]] = {
    400: {
        "INVALID_GEOMETRY": Example(
            summary="Полігон невалідний",
            value=error_example(
                "INVALID_GEOMETRY",
                "Polygon is not valid",
                {"reason": "Self-intersection[30.51 50.41]"},
            ),
        ),
        "FIELD_AREA_TOO_SMALL": Example(
            summary="Площа ≤ 0.1 га",
            value=error_example(
                "FIELD_AREA_TOO_SMALL",
                "Field area must be greater than 0.1 ha",
                {"area_ha": 0.0079, "min_area_ha": 0.1},
            ),
        ),
    },
    404: {
        "FIELD_NOT_FOUND": Example(
            summary="Поле не знайдено",
            value=error_example("FIELD_NOT_FOUND", "Field not found", {"id": FIELD_ID}),
        ),
    },
    422: {
        "VALIDATION_ERROR": Example(
            summary="Невалідні параметри або тіло",
            value=error_example(
                "VALIDATION_ERROR",
                "Request validation failed",
                [
                    {
                        "loc": ["query", "lat"],
                        "msg": "Input should be less than or equal to 90",
                        "type": "less_than_equal",
                    }
                ],
            ),
        ),
    },
    503: {
        "DATABASE_UNAVAILABLE": Example(
            summary="База недоступна",
            value=error_example("DATABASE_UNAVAILABLE", "Database is unavailable"),
        ),
    },
}
