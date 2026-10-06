"""ORM-модель сільськогосподарського поля."""

import uuid
from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    CheckConstraint,
    Computed,
    Double,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Field(Base):
    """Поле: полігон у WGS 84 (SRID 4326) з атрибутами.

    Площу `area_ha` рахує сама база (generated column) на еліпсоїді Землі —
    один раз при записі, тож фільтр за площею — звичайний btree без обчислень.
    """

    __tablename__ = "fields"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(255))
    crop: Mapped[str] = mapped_column(String(100))
    owner: Mapped[str] = mapped_column(String(255), index=True)
    # spatial_index=False: GIST-індекс оголошено явно нижче, з нашим іменем
    geom: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False)
    )
    area_ha: Mapped[float] = mapped_column(
        Double,
        Computed("ST_Area(geom::geography) / 10000", persisted=True),
        index=True,
    )
    # precision=0: час із точністю до секунди, як у прикладі ТЗ
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True, precision=0), server_default=func.now()
    )

    __table_args__ = (
        # Захист у глибину: страхує від запису в обхід API (наприклад, сиди)
        CheckConstraint("ST_IsValid(geom)", name="geom_valid"),
        CheckConstraint("area_ha > 0.1", name="area_min"),
        # Ключовий індекс пошуку за точкою: дерево обмежувальних прямокутників
        Index("ix_fields_geom", "geom", postgresql_using="gist"),
        # Стабільне сортування списку: нові зверху, id — tie-breaker
        Index("ix_fields_created_at_id", created_at.desc(), id.desc()),
    )
