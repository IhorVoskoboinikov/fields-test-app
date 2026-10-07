from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionFactory


async def get_session() -> AsyncIterator[AsyncSession]:
    """Відкриває `AsyncSession` на запит і закриває її після відповіді.

    FastAPI кешує залежність у межах запиту, тож сервіс і репозиторій отримують
    одну й ту саму сесію. Транзакцію відкриває сервіс (`session.begin()`), не тут.
    """
    async with SessionFactory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
