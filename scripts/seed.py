"""Сиди: відтворювані поля в сільгоспобластях України + демо-поля для запитів із ТЗ.

    python -m scripts.seed                       # заповнити порожню базу (2000 полів)
    python -m scripts.seed --truncate            # перестворити дані
    python -m scripts.seed --count 100000 --truncate

Поля вставляються прямо в БД, в обхід API (швидкість); валідність охороняють
CHECK-констрейнти таблиці. Площу `area_ha` рахує сама база.
"""

import argparse
import asyncio
import math
import random
import time
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Field
from app.db.session import create_engine
from app.repositories.field import FieldRepository

METERS_PER_DEGREE_LAT = 111_320
BATCH_SIZE = 1000
COORD_DIGITS = 6  # ~0.1 м

# Центри сільгоспкластерів (lon, lat) — районні центри далеко від великих водойм
# (Кременчуцьке водосховище, Дніпро, Бузький лиман), щоб поля не падали у воду.
# Київщина — навколо Білої Церкви (~80 км від центру Києва): випадкові поля
# фізично не дістають до точки з ТЗ.
CLUSTERS: dict[str, tuple[float, float]] = {
    "Полтавська (Карлівка)": (35.13, 49.46),
    "Вінницька (Тульчин)": (28.85, 48.68),
    "Черкаська (Звенигородка)": (30.97, 49.08),
    "Кіровоградська (Бобринець)": (32.16, 48.06),
    "Хмельницька (Старокостянтинів)": (27.21, 49.76),
    "Житомирська (Бердичів)": (28.59, 49.90),
    "Київська (Біла Церква)": (30.11, 49.80),
    "Харківська (Красноград)": (35.45, 49.37),
    "Дніпропетровська (Павлоград)": (35.87, 48.53),
    "Миколаївська (Баштанка)": (32.44, 47.41),
}
CLUSTER_RADIUS_KM = (30, 50)

CROPS: dict[str, int] = {  # культура → вага (основні частіше)
    "Пшениця": 25,
    "Соняшник": 22,
    "Кукурудза": 20,
    "Ячмінь": 8,
    "Соя": 7,
    "Ріпак": 6,
    "Жито": 3,
    "Овес": 3,
    "Цукровий буряк": 3,
    "Гречка": 3,
}

AREA_HA = (0.5, 300)  # нижня межа гарантує «> 0.1 га»
ASPECT = (1, 4)  # співвідношення сторін
OVERLAP_SHIFT = (0.3, 0.6)  # зсув центру перекриваючого поля, частка розміру базового

SURNAMES = [
    "Іванов", "Петренко", "Коваленко", "Бондаренко", "Шевченко", "Ткаченко", "Кравченко",
    "Олійник", "Мельник", "Поліщук", "Савченко", "Руденко", "Мороз", "Лисенко", "Марченко",
    "Гончаренко", "Литвиненко", "Кравець", "Захарченко", "Павленко", "Бойко", "Ковальчук",
    "Сидоренко", "Тимошенко", "Гриценко",
]  # fmt: skip
INITIALS = "АБВГДЄІКЛМОПРСТ"
COMPANY_NAMES = [
    "Світанок", "Лан", "Колос", "Злагода", "Нива", "Добробут", "Урожай", "Степ", "Поділля",
    "Віра", "Перемога", "Дніпро", "Зоря", "Батьківщина", "Відродження", "Агрія", "Хліб",
    "Росток", "Обрій", "Січ", "Каштан", "Явір", "Джерело", "Берегиня", "Сяйво",
]  # fmt: skip


@dataclass(frozen=True, slots=True)
class Rect:
    """Повернутий прямокутник: центр у градусах, сторони в метрах, кут у радіанах."""

    lon: float
    lat: float
    length_m: float
    width_m: float
    angle: float

    def ring(self) -> list[tuple[float, float]]:
        dlat_per_m = 1 / METERS_PER_DEGREE_LAT
        dlon_per_m = 1 / (METERS_PER_DEGREE_LAT * math.cos(math.radians(self.lat)))
        cos_a, sin_a = math.cos(self.angle), math.sin(self.angle)
        corners = []
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            x, y = sx * self.length_m / 2, sy * self.width_m / 2
            east, north = x * cos_a - y * sin_a, x * sin_a + y * cos_a
            corners.append(
                (
                    round(self.lon + east * dlon_per_m, COORD_DIGITS),
                    round(self.lat + north * dlat_per_m, COORD_DIGITS),
                )
            )
        return [*corners, corners[0]]


@dataclass(frozen=True, slots=True)
class DemoField:
    name: str
    crop: str
    owner: str
    ring: list[tuple[float, float]]


def box(lon1: float, lat1: float, lon2: float, lat2: float) -> list[tuple[float, float]]:
    return [(lon1, lat1), (lon2, lat1), (lon2, lat2), (lon1, lat2), (lon1, lat1)]


# Демо-поля. Координати з ТЗ — центр Києва (Майдан): реальних полів там немає,
# ці поля стоять там лише заради прикладів із ТЗ.
DEMO_FIELDS = [
    # Поле з прикладу ТЗ — дослівно (площа 79.00 га, до точки з ТЗ — 241.7 м)
    DemoField(
        "Поле №1 - Пшениця", "Пшениця", "Іванов І.І.", box(30.5234, 50.4501, 30.5334, 50.4601)
    ),
    # Ще два поля, що перекривають точку з ТЗ (lon=30.5250, lat=50.4550) → 3 збіги
    DemoField(
        "Поле №2 - Соняшник",
        "Соняшник",
        'ТОВ "Агро-Світанок"',
        box(30.5150, 50.4520, 30.5290, 50.4580),
    ),
    DemoField(
        "Поле №3 - Кукурудза", "Кукурудза", 'ФГ "Колос"', box(30.5220, 50.4530, 30.5320, 50.4640)
    ),
    # Два сусідні поля зі спільною межею lon=30.5700: точка на межі знаходить обидва
    DemoField(
        "Поле №4 - Ячмінь", "Ячмінь", "Петренко О.В.", box(30.5600, 50.4700, 30.5700, 50.4800)
    ),
    DemoField("Поле №5 - Соя", "Соя", "Коваленко М.С.", box(30.5700, 50.4700, 30.5800, 50.4800)),
]

DEMO_POINTS = [
    ("приклад ТЗ", 30.5250, 50.4550),
    ("спільна межа", 30.5700, 50.4750),
    ("море", 31.0000, 46.0000),
]


def make_owners(rng: random.Random, count: int = 100) -> list[str]:
    people = {"Іванов І.І."}
    while len(people) < count // 2:
        people.add(f"{rng.choice(SURNAMES)} {rng.choice(INITIALS)}.{rng.choice(INITIALS)}.")
    companies = [f'ТОВ "Агро-{name}"' for name in COMPANY_NAMES]
    farms = [f'ФГ "{name}"' for name in COMPANY_NAMES]
    return sorted(people) + companies + farms


def random_rect(rng: random.Random, lon: float, lat: float) -> Rect:
    """Прямокутник випадкової площі (лог-рівномірно: дрібних полів більше), форми й повороту."""
    area_m2 = math.exp(rng.uniform(math.log(AREA_HA[0]), math.log(AREA_HA[1]))) * 10_000
    aspect = rng.uniform(*ASPECT)
    width = math.sqrt(area_m2 / aspect)
    return Rect(lon, lat, width * aspect, width, rng.uniform(0, math.pi))


def point_in_cluster(rng: random.Random, center: tuple[float, float]) -> tuple[float, float]:
    """Рівномірна випадкова точка в колі радіусом 30–50 км навколо центру кластера."""
    radius_m = rng.uniform(*CLUSTER_RADIUS_KM) * 1000 * math.sqrt(rng.random())
    bearing = rng.uniform(0, 2 * math.pi)
    lon0, lat0 = center
    dlat = radius_m * math.cos(bearing) / METERS_PER_DEGREE_LAT
    dlon = radius_m * math.sin(bearing) / (METERS_PER_DEGREE_LAT * math.cos(math.radians(lat0)))
    return lon0 + dlon, lat0 + dlat


def overlapping_rect(rng: random.Random, base: Rect) -> Rect:
    """Поле, що гарантовано перекриває `base`: центр зсунутий на 30–60% його розміру.

    Зсув задаємо в системі координат базового поля (уздовж його довжини і ширини),
    тож новий центр лежить усередині базового прямокутника.
    """
    shift = rng.uniform(*OVERLAP_SHIFT)
    phi = rng.uniform(0, 2 * math.pi)
    x = shift * base.length_m / 2 * math.cos(phi)
    y = shift * base.width_m / 2 * math.sin(phi)
    cos_a, sin_a = math.cos(base.angle), math.sin(base.angle)
    east, north = x * cos_a - y * sin_a, x * sin_a + y * cos_a
    lon = base.lon + east / (METERS_PER_DEGREE_LAT * math.cos(math.radians(base.lat)))
    lat = base.lat + north / METERS_PER_DEGREE_LAT
    return random_rect(rng, lon, lat)


def to_ewkt(ring: list[tuple[float, float]]) -> str:
    return "SRID=4326;POLYGON((" + ", ".join(f"{lon} {lat}" for lon, lat in ring) + "))"


def generate(count: int, seed: int, overlap_ratio: float) -> tuple[list[dict], int]:
    rng = random.Random(seed)
    owners = make_owners(rng)
    crops, weights = list(CROPS), list(CROPS.values())

    rows = [
        {"name": d.name, "crop": d.crop, "owner": d.owner, "geom": to_ewkt(d.ring)}
        for d in DEMO_FIELDS
    ]
    rects: list[Rect] = []
    overlapping = 0
    for number in range(len(DEMO_FIELDS) + 1, count + 1):
        if rects and rng.random() < overlap_ratio:
            rect = overlapping_rect(rng, rng.choice(rects))
            overlapping += 1
        else:
            rect = random_rect(rng, *point_in_cluster(rng, rng.choice(list(CLUSTERS.values()))))
        rects.append(rect)
        crop = rng.choices(crops, weights)[0]
        rows.append(
            {
                "name": f"Поле №{number} - {crop}",
                "crop": crop,
                "owner": rng.choice(owners),
                "geom": to_ewkt(rect.ring()),
            }
        )
    return rows, overlapping


async def seed(count: int, seed_value: int, truncate: bool, overlap_ratio: float) -> None:
    """Заповнює таблицю `fields`; якщо вона не порожня і немає --truncate — нічого не робить."""
    engine = create_engine()
    try:
        async with engine.begin() as conn:
            if truncate:
                await conn.execute(text("TRUNCATE fields"))
            existing = await conn.scalar(select(func.count()).select_from(Field))
            if existing:
                print(f"Table fields already has {existing} rows — skipping (use --truncate).")
                return

            started = time.perf_counter()
            rows, overlapping = generate(count, seed_value, overlap_ratio)
            for start in range(0, len(rows), BATCH_SIZE):
                await conn.execute(insert(Field), rows[start : start + BATCH_SIZE])
        # ANALYZE поза транзакцією вставки: планувальник одразу бачить свіжу статистику
        async with engine.begin() as conn:
            await conn.execute(text("ANALYZE fields"))
        elapsed = time.perf_counter() - started

        print(f"Seeded {len(rows)} fields in {elapsed:.1f}s (overlapping: {overlapping})")
        by_crop = Counter(row["crop"] for row in rows).most_common()
        print("By crop: " + ", ".join(f"{crop} {n}" for crop, n in by_crop))

        print("Demo points:")
        async with AsyncSession(engine) as session:
            repo = FieldRepository(session)
            for label, lon, lat in DEMO_POINTS:
                matches = await repo.find_by_point(lon, lat)
                print(f"  lon={lon:.4f} lat={lat:.4f}  → {len(matches)} fields  ({label})")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the fields table with test data.")
    parser.add_argument("--count", type=int, default=2000, help="кількість полів (≥ 1000 за ТЗ)")
    parser.add_argument("--seed", type=int, default=42, help="seed генератора — однакові дані")
    parser.add_argument("--truncate", action="store_true", help="очистити таблицю перед вставкою")
    parser.add_argument(
        "--overlap-ratio", type=float, default=0.1, help="частка полів, що перекривають інші"
    )
    args = parser.parse_args()
    if args.count < len(DEMO_FIELDS):
        parser.error(f"--count must be at least {len(DEMO_FIELDS)}")
    asyncio.run(seed(args.count, args.seed, args.truncate, args.overlap_ratio))


if __name__ == "__main__":
    main()
