from typing import Any
from uuid import UUID

MIN_FIELD_AREA_HA = 0.1


class AppError(Exception):
    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "Internal server error"

    def __init__(self, message: str | None = None, details: Any = None) -> None:
        self.message = message or self.message
        self.details = details
        super().__init__(self.message)


class FieldNotFoundError(AppError):
    status_code = 404
    code = "FIELD_NOT_FOUND"
    message = "Field not found"

    def __init__(self, field_id: UUID) -> None:
        super().__init__(details={"id": str(field_id)})


class InvalidGeometryError(AppError):
    """Полігон невалідний за ST_IsValid (самоперетин тощо); reason — з ST_IsValidReason."""

    status_code = 400
    code = "INVALID_GEOMETRY"
    message = "Polygon is not valid"

    def __init__(self, reason: str) -> None:
        super().__init__(details={"reason": reason})


class FieldAreaTooSmallError(AppError):
    status_code = 400
    code = "FIELD_AREA_TOO_SMALL"
    message = f"Field area must be greater than {MIN_FIELD_AREA_HA} ha"

    def __init__(self, area_ha: float) -> None:
        super().__init__(details={"area_ha": round(area_ha, 4), "min_area_ha": MIN_FIELD_AREA_HA})


class DatabaseUnavailableError(AppError):
    status_code = 503
    code = "DATABASE_UNAVAILABLE"
    message = "Database is unavailable"
