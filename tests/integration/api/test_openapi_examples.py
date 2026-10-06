"""Приклади помилок у Swagger збігаються з реальними відповідями застосунку."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.dependencies.db import get_session
from app.openapi.examples import FIELD_CREATE_EXAMPLES, FIELD_ID


def documented_example(app: FastAPI, path: str, method: str, status: int, name: str) -> dict:
    """Приклад помилки з OpenAPI-специфікації (те, що бачить користувач у /docs)."""
    response = app.openapi()["paths"][path][method]["responses"][str(status)]
    return response["content"]["application/json"]["examples"][name]["value"]


def without_request_id(body: dict[str, Any]) -> dict[str, Any]:
    """request_id у кожного запиту свій — порівнюємо все інше."""
    return {"error": {k: v for k, v in body["error"].items() if k != "request_id"}}


@pytest.mark.parametrize(
    ("method", "url", "body", "path", "status", "name"),
    [
        pytest.param(
            "post", "/api/fields", FIELD_CREATE_EXAMPLES["bowtie"]["value"],
            "/api/fields", 400, "INVALID_GEOMETRY", id="create-bowtie",
        ),
        pytest.param(
            "post", "/api/fields", FIELD_CREATE_EXAMPLES["tiny"]["value"],
            "/api/fields", 400, "FIELD_AREA_TOO_SMALL", id="create-tiny",
        ),
        pytest.param(
            "post", "/api/fields", FIELD_CREATE_EXAMPLES["open_ring"]["value"],
            "/api/fields", 422, "VALIDATION_ERROR", id="create-open-ring",
        ),
        pytest.param(
            "get", "/api/fields?crop=", None,
            "/api/fields", 422, "VALIDATION_ERROR", id="list-empty-crop",
        ),
        pytest.param(
            "get", "/api/fields/find-by-point?lon=30.5&lat=100", None,
            "/api/fields/find-by-point", 422, "VALIDATION_ERROR", id="find-lat-100",
        ),
        pytest.param(
            "get", f"/api/fields/{FIELD_ID}", None,
            "/api/fields/{field_id}", 404, "FIELD_NOT_FOUND", id="get-unknown-id",
        ),
        pytest.param(
            "get", "/api/fields/abc", None,
            "/api/fields/{field_id}", 422, "VALIDATION_ERROR", id="get-invalid-id",
        ),
    ],
)  # fmt: skip
async def test_error_examples_match_real_responses(
    app: FastAPI,
    client: AsyncClient,
    method: str,
    url: str,
    body: dict | None,
    path: str,
    status: int,
    name: str,
) -> None:
    response = await client.request(method, url, json=body)

    assert response.status_code == status
    expected = documented_example(app, path, method, status, name)
    assert without_request_id(response.json()) == without_request_id(expected)


async def test_health_503_example_matches_real_response(app: FastAPI, client: AsyncClient) -> None:
    class BrokenSession:
        async def execute(self, *args: Any, **kwargs: Any) -> None:
            raise ConnectionRefusedError("database is down")

    async def broken_session() -> AsyncIterator[BrokenSession]:
        yield BrokenSession()

    app.dependency_overrides[get_session] = broken_session

    response = await client.get("/health")

    assert response.status_code == 503
    expected = documented_example(app, "/health", "get", 503, "DATABASE_UNAVAILABLE")
    assert without_request_id(response.json()) == without_request_id(expected)
