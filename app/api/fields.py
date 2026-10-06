"""Роутер /api/fields — шляхи, параметри і тіла відповідей рівно як у ТЗ."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Query, status

from app.dependencies.services import FieldServiceDep
from app.openapi.examples import FIELD_CREATE_EXAMPLES
from app.openapi.responses import error_responses
from app.schemas.field import (
    FieldCreate,
    FieldListQuery,
    FieldListResponse,
    FieldRead,
    FindByPointResponse,
    PointQuery,
)

router = APIRouter(prefix="/api/fields", tags=["fields"])


@router.post(
    "",
    response_model=FieldRead,
    status_code=status.HTTP_201_CREATED,
    summary="Створити поле",
    description=(
        "Полігон має бути валідним: замкнене кільце (інакше 422), без самоперетинів "
        "(перевіряє `ST_IsValid` у PostGIS, інакше 400), площа більша за 0.1 га (інакше 400). "
        "Площу рахує база на еліпсоїді Землі."
    ),
    responses=error_responses(400, 422, operation="create_field"),
)
async def create_field(
    body: Annotated[FieldCreate, Body(openapi_examples=FIELD_CREATE_EXAMPLES)],
    service: FieldServiceDep,
) -> FieldRead:
    """Створення нового поля."""
    return await service.create_field(body)


@router.get(
    "",
    response_model=FieldListResponse,
    summary="Список полів",
    description=(
        "Фільтри `crop` і `owner` — точний збіг; `min_area` і `max_area` — у гектарах, "
        "включно. Нові поля зверху. Геометрія в списку не повертається."
    ),
    responses=error_responses(422, operation="list_fields"),
)
async def list_fields(
    query: Annotated[FieldListQuery, Query()], service: FieldServiceDep
) -> FieldListResponse:
    """Список полів з фільтрацією та пагінацією."""
    return await service.list_fields(query)


# Важливо: /find-by-point оголошується ВИЩЕ за /{field_id},
# інакше "find-by-point" розпарситься як UUID і поверне 422.
@router.get(
    "/find-by-point",
    response_model=FindByPointResponse,
    summary="Пошук полів за точкою",
    description=(
        "Основний ендпоінт: поля, що містять точку `[lon, lat]` (точка на межі — всередині). "
        "Полів може бути кілька, якщо вони перекриваються; сортування — за відстанню до "
        "центроїда поля. Без збігів — 200 з порожнім `fields`. "
        "`query_time_ms` — час SQL-запиту пошуку (через GIST-індекс)."
    ),
    responses=error_responses(422, operation="find_fields_by_point"),
)
async def find_fields_by_point(
    query: Annotated[PointQuery, Query()], service: FieldServiceDep
) -> FindByPointResponse:
    """Пошук полів, що містять задану точку."""
    return await service.find_by_point(query)


@router.get(
    "/{field_id}",
    response_model=FieldRead,
    summary="Деталі поля",
    description="Поле з повною геометрією (GeoJSON Polygon).",
    responses=error_responses(404, 422, operation="get_field"),
)
async def get_field(field_id: UUID, service: FieldServiceDep) -> FieldRead:
    """Деталі поля з повною геометрією."""
    return await service.get_field(field_id)
