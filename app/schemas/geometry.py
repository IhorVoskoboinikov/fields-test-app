"""GeoJSON-полігон: Pydantic перевіряє форму даних, зміст геометрії перевіряє PostGIS.

Тут ловимо те, що видно без геометричних обчислень (→ 422): тип, діапазон координат,
2D, мінімум 4 точки в кільці, замкнутість кільця, ліміт вершин, ребра шириною ≥ 180°
за довготою (на сфері такі ребра неоднозначні, і `ST_Area(geography)` на них падає).
Самоперетини та інші топологічні помилки ловить `ST_IsValid` у сервісі (→ 400).
"""

from itertools import pairwise
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_VERTICES = 10_000
MIN_RING_POSITIONS = 4
MAX_EDGE_LON_SPAN = 180

Longitude = Annotated[float, Field(ge=-180, le=180)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
# Порядок як у GeoJSON: [lon, lat]; рівно 2 числа — 3D-координати відхиляються
Position = tuple[Longitude, Latitude]


class PolygonGeometry(BaseModel):
    """GeoJSON Polygon: `coordinates = [зовнішнє кільце, *дірки]`.

    Порядок обходу кілець (right-hand rule з RFC 7946) не нав'язуємо.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["Polygon"]
    coordinates: list[list[Position]] = Field(min_length=1)

    @field_validator("coordinates")
    @classmethod
    def check_rings(cls, rings: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
        """Кожне кільце: ≥ 4 точок, замкнене, ребра вужчі за 180° довготи; всього ≤ MAX_VERTICES."""
        total = 0
        for index, ring in enumerate(rings):
            if len(ring) < MIN_RING_POSITIONS:
                raise ValueError(f"ring {index} must have at least {MIN_RING_POSITIONS} positions")
            if ring[0] != ring[-1]:
                raise ValueError(
                    f"ring {index} is not closed: first and last positions must be equal"
                )
            for (lon1, _), (lon2, _) in pairwise(ring):
                if abs(lon2 - lon1) >= MAX_EDGE_LON_SPAN:
                    raise ValueError(
                        f"ring {index} has an edge spanning {MAX_EDGE_LON_SPAN}° "
                        "of longitude or more"
                    )
            total += len(ring)
        if total > MAX_VERTICES:
            raise ValueError(f"polygon must have at most {MAX_VERTICES} vertices, got {total}")
        return rings
