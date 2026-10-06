"""Роутер /api/fields — шляхи, параметри і тіла відповідей рівно як у ТЗ."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.dependencies.services import FieldServiceDep
from app.schemas.field import FieldCreate, FieldListQuery, FieldListResponse, FieldRead

router = APIRouter(prefix="/api/fields", tags=["fields"])


@router.post("", response_model=FieldRead, status_code=status.HTTP_201_CREATED)
async def create_field(body: FieldCreate, service: FieldServiceDep) -> FieldRead:
    """Створення нового поля."""
    return await service.create_field(body)


@router.get("", response_model=FieldListResponse)
async def list_fields(
    query: Annotated[FieldListQuery, Query()], service: FieldServiceDep
) -> FieldListResponse:
    """Список полів з фільтрацією та пагінацією."""
    return await service.list_fields(query)


# Важливо: /find-by-point (етап 5) оголошується ВИЩЕ за /{field_id},
# інакше "find-by-point" розпарситься як UUID і поверне 422.


@router.get("/{field_id}", response_model=FieldRead)
async def get_field(field_id: UUID, service: FieldServiceDep) -> FieldRead:
    """Деталі поля з повною геометрією."""
    return await service.get_field(field_id)
