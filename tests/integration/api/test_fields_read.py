"""GET /api/fields/{id} і GET /api/fields: деталі поля, список, фільтри, пагінація."""

import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import CreateField
from tests.helpers import make_square


async def test_get_field_returns_geometry(client: AsyncClient, create_field: CreateField) -> None:
    created = await create_field()

    response = await client.get(f"/api/fields/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


async def test_get_unknown_field_returns_404(client: AsyncClient) -> None:
    field_id = str(uuid.uuid4())

    response = await client.get(f"/api/fields/{field_id}")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "FIELD_NOT_FOUND"
    assert error["details"] == {"id": field_id}


async def test_get_field_with_invalid_id_returns_422(client: AsyncClient) -> None:
    response = await client.get("/api/fields/abc")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_list_filters_by_crop_and_min_area(
    client: AsyncClient, create_field: CreateField
) -> None:
    # квадрати 1×1 км = 100 га і 0.5×0.5 км = 25 га
    big_wheat = await create_field(crop="Пшениця", geometry=make_square(30.0, 49.0, 1000))
    await create_field(crop="Пшениця", geometry=make_square(30.1, 49.0, 500))
    await create_field(crop="Соя", geometry=make_square(30.2, 49.0, 1000))

    response = await client.get("/api/fields", params={"crop": "Пшениця", "min_area": 50})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [f["id"] for f in body["fields"]] == [big_wheat["id"]]
    # у списку немає геометрії — рівно поля з ТЗ
    assert set(body["fields"][0]) == {"id", "name", "area_ha", "crop", "owner"}


async def test_list_is_newest_first_with_total_and_pagination(
    client: AsyncClient, create_field: CreateField, engine: AsyncEngine
) -> None:
    ids = [(await create_field(name=f"Поле {n}"))["id"] for n in range(3)]
    # різний created_at без sleep: поле n створене на n хвилин пізніше
    async with engine.begin() as conn:
        for minutes, field_id in enumerate(ids):
            await conn.execute(
                text(
                    "UPDATE fields SET created_at = now() + make_interval(mins => :m) "
                    "WHERE id = :id"
                ),
                {"m": minutes, "id": field_id},
            )

    first_page = (await client.get("/api/fields", params={"limit": 2})).json()
    second_page = (await client.get("/api/fields", params={"limit": 2, "offset": 2})).json()

    assert first_page["total"] == second_page["total"] == 3
    assert [f["id"] for f in first_page["fields"]] == [ids[2], ids[1]]
    assert [f["id"] for f in second_page["fields"]] == [ids[0]]


async def test_list_offset_past_end_returns_empty_page_with_total(
    client: AsyncClient, create_field: CreateField
) -> None:
    await create_field()

    response = await client.get("/api/fields", params={"offset": 10})

    assert response.status_code == 200
    assert response.json() == {"total": 1, "fields": []}


async def test_list_rejects_empty_crop(client: AsyncClient) -> None:
    response = await client.get("/api/fields?crop=")

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["loc"] == ["query", "crop"]


async def test_list_rejects_min_area_greater_than_max_area(client: AsyncClient) -> None:
    response = await client.get("/api/fields", params={"min_area": 10, "max_area": 1})

    assert response.status_code == 422
