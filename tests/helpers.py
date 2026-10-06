"""Спільні дані для тестів: квадрати заданого розміру і невалідні полігони."""

import math
from typing import Any

METERS_PER_DEGREE_LAT = 111_320


def make_square(lon: float, lat: float, side_m: float) -> dict[str, Any]:
    """GeoJSON-квадрат зі стороною `side_m` метрів; (lon, lat) — південно-західний кут."""
    dlat = side_m / METERS_PER_DEGREE_LAT
    dlon = side_m / (METERS_PER_DEGREE_LAT * math.cos(math.radians(lat)))
    ring = [[lon, lat], [lon + dlon, lat], [lon + dlon, lat + dlat], [lon, lat + dlat], [lon, lat]]
    return {"type": "Polygon", "coordinates": [ring]}


def polygon(*ring: tuple[float, float]) -> dict[str, Any]:
    """GeoJSON Polygon з одного кільця."""
    return {"type": "Polygon", "coordinates": [[list(point) for point in ring]]}


# Поле з прикладу ТЗ
TZ_GEOMETRY = polygon(
    (30.5234, 50.4501),
    (30.5334, 50.4501),
    (30.5334, 50.4601),
    (30.5234, 50.4601),
    (30.5234, 50.4501),
)
TZ_FIELD = {
    "name": "Поле №1 - Пшениця",
    "geometry": TZ_GEOMETRY,
    "crop": "Пшениця",
    "owner": "Іванов І.І.",
}
TZ_POINT = {"lon": 30.5250, "lat": 50.4550}

# «Метелик» (вісімка): сторони перетинаються
BOWTIE = polygon((30.0, 50.0), (30.02, 50.02), (30.02, 50.0), (30.0, 50.02), (30.0, 50.0))

# Маленька петля біля увігнутого кута (armpit)
ARMPIT = polygon(
    (30.0, 50.0), (30.02, 50.0), (30.02, 50.02), (30.01, 50.02), (30.01, 50.01),
    (30.012, 50.012), (30.012, 50.008), (30.01, 50.01), (30.0, 50.02), (30.0, 50.0),
)  # fmt: skip

# Квадрат ~7 × 11 м — близько 0.008 га
TINY = polygon((30.0, 50.0), (30.0001, 50.0), (30.0001, 50.0001), (30.0, 50.0001), (30.0, 50.0))

# Кільце не замкнене: остання точка не дорівнює першій
OPEN_RING = polygon((30.0, 50.0), (30.02, 50.0), (30.02, 50.02), (30.0, 50.02))

# Довгота поза діапазоном
LON_200 = polygon((200.0, 50.0), (30.02, 50.0), (30.02, 50.02), (200.0, 50.0))
