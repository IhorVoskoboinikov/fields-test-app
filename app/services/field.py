"""Бізнес-логіка полів: валідація геометрії й площі, межі транзакцій."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    MIN_FIELD_AREA_HA,
    FieldAreaTooSmallError,
    FieldNotFoundError,
    InvalidGeometryError,
)
from app.core.logger import get_logger
from app.repositories.field import FieldFilters, FieldRepository
from app.schemas.field import (
    FieldCreate,
    FieldListItem,
    FieldListQuery,
    FieldListResponse,
    FieldRead,
)

logger = get_logger(__name__)


class FieldService:
    """Операції з полями. Транзакцію відкриває сервіс (`session.begin()`), не репозиторій."""

    def __init__(self, session: AsyncSession, repo: FieldRepository) -> None:
        self.session = session
        self.repo = repo

    async def create_field(self, data: FieldCreate) -> FieldRead:
        """Створює поле, якщо полігон валідний і його площа більша за 0.1 га.

        Порядок перевірок важливий: спершу ST_IsValid, потім площа. У «метелика»
        (самоперетин) площа на еліпсоїді дорівнює 0 — без цього порядку він
        отримав би помилку «замала площа» замість «невалідний полігон».
        """
        geojson = data.geometry.model_dump_json()
        async with self.session.begin():
            check = await self.repo.check_geometry(geojson)
            if not check.is_valid:
                raise InvalidGeometryError(check.reason)
            if check.area_ha is None or check.area_ha <= MIN_FIELD_AREA_HA:
                raise FieldAreaTooSmallError(check.area_ha or 0.0)
            row = await self.repo.create(
                name=data.name, crop=data.crop, owner=data.owner, geojson=geojson
            )
        logger.info("field created id=%s area_ha=%.2f", row["id"], row["area_ha"])
        return FieldRead.model_validate(row)

    async def get_field(self, field_id: UUID) -> FieldRead:
        """Поле з повною геометрією; немає такого id → FieldNotFoundError."""
        async with self.session.begin():
            row = await self.repo.get_by_id(field_id)
        if row is None:
            raise FieldNotFoundError(field_id)
        return FieldRead.model_validate(row)

    async def list_fields(self, query: FieldListQuery) -> FieldListResponse:
        """Сторінка полів з фільтрами і загальною кількістю, нові зверху."""
        filters = FieldFilters(
            crop=query.crop, owner=query.owner, min_area=query.min_area, max_area=query.max_area
        )
        async with self.session.begin():
            total, rows = await self.repo.list_page(filters, limit=query.limit, offset=query.offset)
        return FieldListResponse(
            total=total, fields=[FieldListItem.model_validate(row) for row in rows]
        )
