from dataclasses import dataclass
from typing import Any
from uuid import UUID

from geoalchemy2 import Geography
from sqlalchemy import JSON, Select, case, cast, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Field

# Каст у geography для метрів на еліпсоїді (`::geography`); SRID явно, інакше
# GeoAlchemy2 рендерить geography(GEOMETRY,-1) і PostGIS пише NOTICE
GEOGRAPHY = Geography(srid=4326)

GEOMETRY_JSON = cast(func.ST_AsGeoJSON(Field.geom), JSON).label("geometry")

LIST_COLUMNS = (Field.id, Field.name, Field.area_ha, Field.crop, Field.owner)
DETAIL_COLUMNS = (*LIST_COLUMNS, Field.created_at, GEOMETRY_JSON)


@dataclass(frozen=True, slots=True)
class GeometryCheck:
    is_valid: bool
    reason: str
    area_ha: float | None  # None для невалідного полігона


@dataclass(frozen=True, slots=True)
class FieldFilters:
    crop: str | None = None
    owner: str | None = None
    min_area: float | None = None
    max_area: float | None = None


class FieldRepository:
    """Запити до `fields`. Транзакцією керує сервіс, репозиторій лише виконує SQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def check_geometry(self, geojson: str) -> GeometryCheck:
        """Перевіряє полігон без вставки: валідність, причина помилки і площа в гектарах.

        SELECT ST_IsValid(geom), ST_IsValidReason(geom),
               CASE WHEN ST_IsValid(geom) THEN ST_Area(geom::geography) / 10000 END
        FROM (SELECT ST_GeomFromGeoJSON(:geojson) AS geom) AS input

        Площу рахуємо лише для валідного полігона: на невалідному `ST_Area` може
        впасти з помилкою, і замість 400 INVALID_GEOMETRY вийшов би 500.
        """
        source = select(func.ST_GeomFromGeoJSON(geojson).label("geom")).subquery("input")
        geom = source.c.geom
        stmt = select(
            func.ST_IsValid(geom).label("is_valid"),
            func.ST_IsValidReason(geom).label("reason"),
            case((func.ST_IsValid(geom), func.ST_Area(cast(geom, GEOGRAPHY)) / 10000)).label(
                "area_ha"
            ),
        )
        row = (await self.session.execute(stmt)).one()
        return GeometryCheck(is_valid=row.is_valid, reason=row.reason, area_ha=row.area_ha)

    async def create(self, *, name: str, crop: str, owner: str, geojson: str) -> dict[str, Any]:
        """Вставляє поле; `id`, `area_ha` і `created_at` заповнює база.

        INSERT INTO fields (name, crop, owner, geom)
        VALUES (:name, :crop, :owner, ST_GeomFromGeoJSON(:geojson))
        RETURNING id, name, area_ha, crop, owner, created_at, ST_AsGeoJSON(geom)::json
        """
        stmt = (
            insert(Field)
            .values(name=name, crop=crop, owner=owner, geom=func.ST_GeomFromGeoJSON(geojson))
            .returning(*DETAIL_COLUMNS)
        )
        row = (await self.session.execute(stmt)).mappings().one()
        return dict(row)

    async def get_by_id(self, field_id: UUID) -> dict[str, Any] | None:
        stmt = select(*DETAIL_COLUMNS).where(Field.id == field_id)
        row = (await self.session.execute(stmt)).mappings().one_or_none()
        return dict(row) if row else None

    async def list_page(
        self, filters: FieldFilters, *, limit: int, offset: int
    ) -> tuple[int, list[dict[str, Any]]]:
        """Сторінка списку і загальна кількість — двома запитами з однаковим WHERE.

        Не `count(*) OVER()`: якщо `offset` більший за кількість рядків, сторінка
        порожня і `total` узяти нізвідки. Сортування обов'язкове — без нього
        offset-пагінація недетермінована.
        """
        count_stmt = self._apply_filters(select(func.count()).select_from(Field), filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        page_stmt = (
            self._apply_filters(select(*LIST_COLUMNS), filters)
            .order_by(Field.created_at.desc(), Field.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(page_stmt)).mappings().all()
        return total, [dict(row) for row in rows]

    async def find_by_point(self, lon: float, lat: float) -> list[dict[str, Any]]:
        """Поля, що містять точку, від найближчого центру до найдальшого.

        SELECT id, name, area_ha, crop, owner,
               ST_Distance(ST_Centroid(geom)::geography, point::geography) AS distance_to_center_m
        FROM fields
        WHERE ST_Intersects(geom, point)
        ORDER BY distance_to_center_m

        `ST_Intersects` неявно додає індексну умову `geom && point`: GIST-індекс швидко
        відбирає поля, чий обмежувальний прямокутник містить точку, і точна перевірка
        йде лише для них. Колонка `geom` у WHERE «гола» — усі перетворення лише над
        точкою, інакше індекс не спрацює. Точка на межі поля вважається всередині
        (на відміну від `ST_Contains`). Центроїд і відстань (у метрах, на еліпсоїді)
        рахуються лише для знайдених рядків.
        """
        point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
        distance = func.ST_Distance(
            cast(func.ST_Centroid(Field.geom), GEOGRAPHY), cast(point, GEOGRAPHY)
        ).label("distance_to_center_m")
        stmt = (
            select(*LIST_COLUMNS, distance)
            .where(func.ST_Intersects(Field.geom, point))
            .order_by(distance)
        )
        rows = (await self.session.execute(stmt)).mappings().all()
        return [dict(row) for row in rows]

    @staticmethod
    def _apply_filters(stmt: Select, filters: FieldFilters) -> Select:
        if filters.crop is not None:
            stmt = stmt.where(Field.crop == filters.crop)
        if filters.owner is not None:
            stmt = stmt.where(Field.owner == filters.owner)
        if filters.min_area is not None:
            stmt = stmt.where(Field.area_ha >= filters.min_area)
        if filters.max_area is not None:
            stmt = stmt.where(Field.area_ha <= filters.max_area)
        return stmt
