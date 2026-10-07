from httpx import AsyncClient


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_request_id_is_propagated(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "demo-123"})

    assert response.headers["X-Request-ID"] == "demo-123"


async def test_unknown_route_uses_error_format(client: AsyncClient) -> None:
    response = await client.get("/nope")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert response.headers["X-Request-ID"]
