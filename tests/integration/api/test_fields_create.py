import re

import pytest
from httpx import AsyncClient

from tests.helpers import ARMPIT, BOWTIE, LON_200, OPEN_RING, TASK_FIELD, TINY, polygon


async def test_create_field_from_task_example(client: AsyncClient) -> None:
    response = await client.post("/api/fields", json=TASK_FIELD)

    assert response.status_code == 201
    assert response.headers["X-Request-ID"]
    body = response.json()
    assert body["name"] == TASK_FIELD["name"]
    assert body["crop"] == TASK_FIELD["crop"]
    assert body["owner"] == TASK_FIELD["owner"]
    assert body["geometry"] == TASK_FIELD["geometry"]
    # Площа квадрата з ТЗ на еліпсоїді — 79.00 га (у прикладі ТЗ число ілюстративне)
    assert body["area_ha"] == pytest.approx(79.0, rel=0.01)
    # Формат як у ТЗ: "2024-01-15T10:30:00Z"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", body["created_at"])


async def test_create_field_strips_whitespace(client: AsyncClient) -> None:
    response = await client.post("/api/fields", json={**TASK_FIELD, "name": "  Поле  "})

    assert response.status_code == 201
    assert response.json()["name"] == "Поле"


@pytest.mark.parametrize(
    ("geometry", "status_code", "code"),
    [
        pytest.param(BOWTIE, 400, "INVALID_GEOMETRY", id="bowtie"),
        pytest.param(ARMPIT, 400, "INVALID_GEOMETRY", id="armpit"),
        pytest.param(TINY, 400, "FIELD_AREA_TOO_SMALL", id="tiny"),
        pytest.param(OPEN_RING, 422, "VALIDATION_ERROR", id="open-ring"),
        pytest.param(LON_200, 422, "VALIDATION_ERROR", id="lon-200"),
        pytest.param(
            polygon((0, 0), (180, 0), (180, 1), (0, 1), (0, 0)),
            422,
            "VALIDATION_ERROR",
            id="edge-180-deg",
        ),
    ],
)
async def test_create_field_rejects_invalid_polygon(
    client: AsyncClient, geometry: dict, status_code: int, code: str
) -> None:
    response = await client.post("/api/fields", json={**TASK_FIELD, "geometry": geometry})

    assert response.status_code == status_code
    error = response.json()["error"]
    assert error["code"] == code
    # request_id у тілі помилки збігається із заголовком — по ньому шукаємо в логах
    assert error["request_id"] == response.headers["X-Request-ID"]


async def test_invalid_geometry_reports_reason_with_location(client: AsyncClient) -> None:
    response = await client.post("/api/fields", json={**TASK_FIELD, "geometry": BOWTIE})

    assert response.json()["error"]["details"]["reason"] == "Self-intersection[30.01 50.01]"


@pytest.mark.parametrize(
    "patch",
    [
        pytest.param({"name": ""}, id="empty-name"),
        pytest.param({"crop": "a\u0000b"}, id="nul-in-crop"),
        pytest.param({"color": "red"}, id="extra-key"),
        pytest.param({"geometry": {"type": "Point", "coordinates": [30.5, 50.4]}}, id="point"),
    ],
)
async def test_create_field_validates_body(client: AsyncClient, patch: dict) -> None:
    response = await client.post("/api/fields", json={**TASK_FIELD, **patch})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
