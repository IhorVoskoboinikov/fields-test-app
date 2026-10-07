from typing import Annotated

from fastapi import Depends

from app.dependencies.db import SessionDep
from app.repositories.field import FieldRepository
from app.services.field import FieldService


def get_field_repository(session: SessionDep) -> FieldRepository:
    return FieldRepository(session)


def get_field_service(
    session: SessionDep,
    repo: Annotated[FieldRepository, Depends(get_field_repository)],
) -> FieldService:
    return FieldService(session=session, repo=repo)


FieldServiceDep = Annotated[FieldService, Depends(get_field_service)]
