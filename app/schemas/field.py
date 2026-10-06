"""Схеми полів: тіла запитів і відповідей рівно як у ТЗ, query-параметри моделями."""

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    model_validator,
)

from app.schemas.geometry import Latitude, Longitude, PolygonGeometry

# PostgreSQL не зберігає символ NUL (0x00) у тексті — відхиляємо його ще в Pydantic (422)
NO_NUL = r"^[^\x00]*$"

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255, pattern=NO_NUL)
]
Crop = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=NO_NUL)
]
Owner = Name

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
# Розумна межа offset: більші значення asyncpg не передасть як bigint (було б 500)
MAX_OFFSET = 1_000_000


class FieldCreate(BaseModel):
    """Тіло POST /api/fields."""

    model_config = ConfigDict(extra="forbid")

    name: Name
    geometry: PolygonGeometry
    crop: Crop
    owner: Owner


class FieldListItem(BaseModel):
    """Поле в списку — без геометрії (менше даних із БД і по мережі)."""

    id: UUID = Field(examples=["8c7ff87a-cabd-48fa-bf7c-b47f94edc665"])
    name: str = Field(examples=["Поле №1 - Пшениця"])
    area_ha: float = Field(description="Площа, га", examples=[79.0])
    crop: str = Field(examples=["Пшениця"])
    owner: str = Field(examples=["Іванов І.І."])

    @field_serializer("area_ha")
    def round_area(self, value: float) -> float:
        """Площа в гектарах з точністю до 0.01 га."""
        return round(value, 2)


class FieldRead(FieldListItem):
    """Поле з повною геометрією: відповідь GET /api/fields/{id} і POST /api/fields."""

    geometry: PolygonGeometry
    created_at: datetime = Field(examples=["2026-10-06T07:04:06Z"])


class FieldListResponse(BaseModel):
    """Відповідь GET /api/fields рівно як у ТЗ: `{total, fields}`."""

    total: int = Field(description="Кількість полів з урахуванням фільтрів", examples=[2001])
    fields: list[FieldListItem]


class FieldListQuery(BaseModel):
    """Query-параметри списку. Порожнє значення фільтра (`crop=`) → 422."""

    crop: str | None = Field(
        None, min_length=1, pattern=NO_NUL, description="Культура, точний збіг"
    )
    owner: str | None = Field(
        None, min_length=1, pattern=NO_NUL, description="Власник, точний збіг"
    )
    min_area: float | None = Field(None, ge=0, description="Мінімальна площа, га (включно)")
    max_area: float | None = Field(None, ge=0, description="Максимальна площа, га (включно)")
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Розмір сторінки")
    offset: int = Field(0, ge=0, le=MAX_OFFSET, description="Скільки полів пропустити")

    @model_validator(mode="after")
    def check_area_range(self) -> Self:
        """`min_area` не може бути більшим за `max_area`."""
        if (
            self.min_area is not None
            and self.max_area is not None
            and self.min_area > self.max_area
        ):
            raise ValueError("min_area must be less than or equal to max_area")
        return self


class FieldMatch(FieldListItem):
    """Поле, що містить точку, з відстанню від точки до центроїда поля."""

    distance_to_center_m: float = Field(
        description="Відстань від точки до центроїда поля, м", examples=[241.7]
    )

    @field_serializer("distance_to_center_m")
    def round_distance(self, value: float) -> float:
        """Відстань у метрах з точністю до 0.1 м."""
        return round(value, 1)


class PointOut(BaseModel):
    """Точка запиту у відповіді пошуку."""

    lon: float = Field(examples=[30.525])
    lat: float = Field(examples=[50.455])


class FindByPointResponse(BaseModel):
    """Відповідь GET /api/fields/find-by-point рівно як у ТЗ."""

    query_point: PointOut
    fields: list[FieldMatch]
    query_time_ms: float = Field(description="Час SQL-запиту пошуку, мс", examples=[1.35])

    @field_serializer("query_time_ms")
    def round_query_time(self, value: float) -> float:
        """Час SQL-запиту пошуку в мілісекундах з точністю до 0.01 мс."""
        return round(value, 2)


class PointQuery(BaseModel):
    """Query-параметри пошуку за точкою: обидва обов'язкові."""

    lon: Longitude = Field(description="Довгота, −180…180", examples=[30.5250])
    lat: Latitude = Field(description="Широта, −90…90", examples=[50.4550])
