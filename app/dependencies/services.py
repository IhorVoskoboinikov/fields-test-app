"""Ланцюжок DI: сесія → репозиторій → сервіс (одна й та сама сесія в межах запиту)."""

from typing import Annotated

from fastapi import Depends

from app.dependencies.db import SessionDep
from app.repositories.field import FieldRepository
from app.services.field import FieldService


def get_field_repository(session: SessionDep) -> FieldRepository:
    """Репозиторій полів на сесії поточного запиту."""
    return FieldRepository(session)


def get_field_service(
    session: SessionDep,
    repo: Annotated[FieldRepository, Depends(get_field_repository)],
) -> FieldService:
    """Сервіс полів; FastAPI кешує `get_session`, тож сесія та сама, що в репозиторії."""
    return FieldService(session=session, repo=repo)


FieldServiceDep = Annotated[FieldService, Depends(get_field_service)]
