from httpx import AsyncClient

from tests.conftest import CreateField
from tests.helpers import TASK_POINT, make_square, polygon


async def test_find_by_point_returns_overlapping_fields(
    client: AsyncClient, create_field: CreateField
) -> None:
    # два квадрати 1×1 км з центрами поруч — вони перекриваються
    await create_field(geometry=make_square(30.520, 50.450, side_m=1000))
    await create_field(geometry=make_square(30.525, 50.455, side_m=1000))

    response = await client.get("/api/fields/find-by-point", params={"lon": 30.527, "lat": 50.456})

    assert response.status_code == 200
    body = response.json()
    assert body["query_point"] == {"lon": 30.527, "lat": 50.456}
    assert body["query_time_ms"] >= 0
    distances = [f["distance_to_center_m"] for f in body["fields"]]
    assert len(distances) == 2
    assert distances == sorted(distances)


async def test_find_by_point_task_example(client: AsyncClient, create_field: CreateField) -> None:
    created = await create_field()

    response = await client.get("/api/fields/find-by-point", params=TASK_POINT)

    fields = response.json()["fields"]
    assert [f["id"] for f in fields] == [created["id"]]
    # відстань від точки з ТЗ до центроїда поля з ТЗ на еліпсоїді
    assert fields[0]["distance_to_center_m"] == 241.7
    assert set(fields[0]) == {"id", "name", "area_ha", "crop", "owner", "distance_to_center_m"}


async def test_point_on_shared_border_matches_both_fields(
    client: AsyncClient, create_field: CreateField
) -> None:
    await create_field(
        geometry=polygon((31.0, 49.0), (31.01, 49.0), (31.01, 49.01), (31.0, 49.01), (31.0, 49.0))
    )
    await create_field(
        geometry=polygon(
            (31.01, 49.0), (31.02, 49.0), (31.02, 49.01), (31.01, 49.01), (31.01, 49.0)
        )
    )

    response = await client.get("/api/fields/find-by-point", params={"lon": 31.01, "lat": 49.005})

    assert len(response.json()["fields"]) == 2


async def test_point_outside_fields_returns_empty_list(
    client: AsyncClient, create_field: CreateField
) -> None:
    await create_field()

    response = await client.get("/api/fields/find-by-point", params={"lon": 31.0, "lat": 46.0})

    assert response.status_code == 200
    assert response.json()["fields"] == []


async def test_find_by_point_validates_coordinates(client: AsyncClient) -> None:
    response = await client.get("/api/fields/find-by-point", params={"lon": 30.5, "lat": 100})

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["loc"] == ["query", "lat"]


async def test_find_by_point_requires_both_coordinates(client: AsyncClient) -> None:
    response = await client.get("/api/fields/find-by-point", params={"lon": 30.5})

    assert response.status_code == 422
