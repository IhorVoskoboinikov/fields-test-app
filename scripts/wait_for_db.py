"""Чекає, поки PostgreSQL прийме з'єднання і матиме доступне розширення PostGIS.

Запускається перед міграціями: `python -m scripts.wait_for_db`.
Використовує той самий SQLAlchemy-engine і URL, що й застосунок, — тож
перевіряє саме нашу базу з нашими обліковими даними.
"""

import asyncio
import logging
import sys

from sqlalchemy import text

from app.db.session import create_engine

MAX_ATTEMPTS = 30
DELAY_SECONDS = 1.5

logger = logging.getLogger("wait_for_db")


async def check_db() -> None:
    engine = create_engine()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            postgis = await conn.scalar(
                text("SELECT 1 FROM pg_available_extensions WHERE name = 'postgis'")
            )
            if postgis is None:
                raise RuntimeError("розширення postgis недоступне в цьому PostgreSQL")
    finally:
        await engine.dispose()


async def wait_for_db() -> bool:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            await check_db()
        except Exception as exc:
            logger.warning("Спроба %d/%d: база не готова (%s)", attempt, MAX_ATTEMPTS, exc)
            await asyncio.sleep(DELAY_SECONDS)
        else:
            logger.info("База готова (спроба %d/%d)", attempt, MAX_ATTEMPTS)
            return True
    return False


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if not asyncio.run(wait_for_db()):
        logger.error("База недоступна після %d спроб", MAX_ATTEMPTS)
        sys.exit(1)


if __name__ == "__main__":
    main()
