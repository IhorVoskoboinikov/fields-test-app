"""Бенчмарк пошуку за точкою: лише SQL-запит (те саме, що `query_time_ms`), p50 і p95.

    python -m scripts.benchmark                # з GIST-індексом і без нього
    python -m scripts.benchmark --points 200 --mode no-index

Точки: половина гарантовано всередині наявних полів (`ST_PointOnSurface`),
половина — випадково по сільгоспкластерах із сидів. «Без індексу» — індекс не
видаляємо, а вимикаємо в сесії (`enable_indexscan`, `enable_bitmapscan` = off).
"""

import argparse
import asyncio
import random
import statistics
import time

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Field
from app.db.session import create_engine
from app.repositories.field import FieldRepository
from scripts.seed import CLUSTERS, point_in_cluster

Point = tuple[float, float]


async def make_points(engine: AsyncEngine, count: int, seed: int) -> list[Point]:
    rng = random.Random(seed)
    surface = func.ST_PointOnSurface(Field.geom)
    async with engine.connect() as conn:
        rows = (await conn.execute(select(func.ST_X(surface), func.ST_Y(surface)))).all()
    if not rows:
        raise SystemExit("Table fields is empty — run the seed first.")
    inside = [(lon, lat) for lon, lat in rng.choices(rows, k=count // 2)]
    centers = list(CLUSTERS.values())
    random_points = [point_in_cluster(rng, rng.choice(centers)) for _ in range(count - len(inside))]
    points = inside + random_points
    rng.shuffle(points)
    return points


async def run(points: list[Point], use_index: bool) -> dict[str, float]:
    """Виконує пошук для кожної точки на одному з'єднанні й повертає статистику в мс.

    Кожен режим — на новому engine (новому з'єднанні): asyncpg використовує
    prepared statements, і PostgreSQL кешує для них generic-план. Зміна
    `enable_indexscan` цей кеш не скидає — на старому з'єднанні «без індексу»
    насправді виконувався б план з індексом.
    """
    engine = create_engine()
    timings: list[float] = []
    matches = 0
    async with engine.connect() as conn:
        if not use_index:
            await conn.execute(text("SET enable_indexscan = off"))
            await conn.execute(text("SET enable_bitmapscan = off"))
        repo = FieldRepository(AsyncSession(bind=conn))
        await repo.find_by_point(*points[0])  # прогрів: план і кеш з'єднання
        for lon, lat in points:
            started = time.perf_counter()
            rows = await repo.find_by_point(lon, lat)
            timings.append((time.perf_counter() - started) * 1000)
            matches += len(rows)
        await conn.rollback()
    await engine.dispose()
    quantiles = statistics.quantiles(timings, n=100)
    return {
        "p50": statistics.median(timings),
        "p95": quantiles[94],
        "mean": statistics.fmean(timings),
        "matches": matches / len(points),
    }


async def main_async(points_count: int, mode: str, seed: int) -> None:
    engine = create_engine()
    try:
        async with engine.connect() as conn:
            total = await conn.scalar(select(func.count()).select_from(Field))
        points = await make_points(engine, points_count, seed)
        modes = {"both": [True, False], "index": [True], "no-index": [False]}[mode]

        print(f"Fields: {total}, points: {len(points)} (half inside fields)")
        print("| Полів | Індекс | p50, мс | p95, мс | середнє, мс | збігів на точку |")
        print("| --- | --- | --- | --- | --- | --- |")
        for use_index in modes:
            stats = await run(points, use_index)
            label = "GIST" if use_index else "немає"
            print(
                f"| {total:,} | {label} | {stats['p50']:.2f} | {stats['p95']:.2f} "
                f"| {stats['mean']:.2f} | {stats['matches']:.2f} |".replace(",", " ")
            )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark find-by-point SQL query.")
    parser.add_argument("--points", type=int, default=1000, help="кількість точок запиту")
    parser.add_argument("--mode", choices=["both", "index", "no-index"], default="both")
    parser.add_argument("--seed", type=int, default=7, help="seed генератора точок")
    args = parser.parse_args()
    asyncio.run(main_async(args.points, args.mode, args.seed))


if __name__ == "__main__":
    main()
