"""Бізнес-логіка полів: валідація геометрії й площі, межі транзакцій."""

import time
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
    FieldMatch,
    FieldRead,
    FindByPointResponse,
    PointOut,
    PointQuery,
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
        (самоперетин) частини з протилежним обходом віднімаються: у симетричного
        площа дорівнює 0 («замала площа» замість «невалідний полігон»), а
        несиметричний без цієї перевірки взагалі пройшов би перевірку площі.
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
        """Сторінка полів з фільтрами і загальною кількістю, нові зверху.

        `count(*)` і сторінка — два запити. REPEATABLE READ дає їм один знімок даних:
        на типовому READ COMMITTED кожен запит бачив би свій знімок, і вставка між
        ними розвела б `total` і сторінку.
        """
        filters = FieldFilters(
            crop=query.crop, owner=query.owner, min_area=query.min_area, max_area=query.max_area
        )
        async with self.session.begin():
            await self.session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            total, rows = await self.repo.list_page(filters, limit=query.limit, offset=query.offset)
        return FieldListResponse(
            total=total, fields=[FieldListItem.model_validate(row) for row in rows]
        )

    async def find_by_point(self, query: PointQuery) -> FindByPointResponse:
        """Поля, що містять точку (може бути кілька, якщо поля перекриваються).

        Один SELECT транзакції не потребує, тож виконуємо його в AUTOCOMMIT: драйвер
        не надсилає BEGIN/COMMIT (мінус два round-trip на кожен пошук). З'єднання з
        пулу беремо до заміру, тому `query_time_ms` — час лише SQL-запиту пошуку.
        Немає збігів → порожній список, а не 404.
        """
        async with self.session.begin():
            await self.session.connection(execution_options={"isolation_level": "AUTOCOMMIT"})
            started = time.perf_counter()
            rows = await self.repo.find_by_point(query.lon, query.lat)
            query_time_ms = (time.perf_counter() - started) * 1000
        logger.info("find_by_point matches=%d query_time_ms=%.2f", len(rows), query_time_ms)
        return FindByPointResponse(
            query_point=PointOut(lon=query.lon, lat=query.lat),
            fields=[FieldMatch.model_validate(row) for row in rows],
            query_time_ms=query_time_ms,
        )
