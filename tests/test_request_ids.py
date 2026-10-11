from collections.abc import Iterator
from uuid import UUID

import anyio
import httpx2
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from evidenceguard_api.app import create_app
from evidenceguard_observability.context import current_request_id


def _app_with_test_routes() -> FastAPI:
    app = create_app()

    @app.get("/test-only/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/test-only/boom")
    def boom() -> None:
        raise RuntimeError("test failure")

    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(_app_with_test_routes(), raise_server_exceptions=False) as test_client:
        yield test_client


def _header_id(response: httpx2.Response) -> UUID:
    return UUID(response.headers["X-Request-ID"])


def test_request_id_is_generated_when_absent(client: TestClient) -> None:
    first = client.get("/healthz")
    second = client.get("/healthz")

    assert _header_id(first).version == 4
    assert _header_id(first) != _header_id(second)


@pytest.mark.parametrize(
    "incoming",
    [
        "550e8400-e29b-41d4-a716-446655440000",
        "550E8400-E29B-41D4-A716-446655440000",
        "{550e8400-e29b-41d4-a716-446655440000}",
        "550e8400e29b41d4a716446655440000",
    ],
)
def test_valid_incoming_request_id_is_accepted_and_normalized(
    client: TestClient, incoming: str
) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": incoming})

    assert response.headers["X-Request-ID"] == "550e8400-e29b-41d4-a716-446655440000"


@pytest.mark.parametrize(
    "incoming",
    ["not-a-uuid", "", "1234", "550e8400-e29b-41d4-a716-446655440000" + "0" * 40],
)
def test_invalid_incoming_request_id_is_replaced(client: TestClient, incoming: str) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": incoming})

    returned = response.headers["X-Request-ID"]
    assert returned != incoming
    assert UUID(returned).version == 4


def test_repeated_request_id_headers_are_replaced(client: TestClient) -> None:
    supplied = ["550e8400-e29b-41d4-a716-446655440000", "6ba7b810-9dad-11d1-80b4-00c04fd430c8"]

    response = client.get("/healthz", headers=[("X-Request-ID", value) for value in supplied])

    assert response.headers["X-Request-ID"] not in supplied


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("/healthz", 200),
        ("/test-only/missing", 404),
        ("/test-only/items/not-an-int", 422),
        ("/test-only/boom", 500),
    ],
)
def test_supplied_request_id_is_returned_on_every_outcome(
    client: TestClient, path: str, status: int
) -> None:
    supplied = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"

    response = client.get(path, headers={"X-Request-ID": supplied})

    assert response.status_code == status
    assert response.headers["X-Request-ID"] == supplied
    if status >= 400:
        assert response.json()["request_id"] == supplied


def test_handlers_see_their_own_request_id() -> None:
    app = create_app()

    @app.get("/test-only/whoami")
    def whoami(request: Request) -> dict[str, str]:
        return {"context": str(current_request_id()), "state": str(request.state.request_id)}

    supplied = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    body = TestClient(app).get("/test-only/whoami", headers={"X-Request-ID": supplied}).json()

    assert body == {"context": supplied, "state": supplied}
    assert current_request_id() is None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_concurrent_requests_keep_their_own_request_ids() -> None:
    app = create_app()
    count = 10
    arrived = 0
    all_arrived = anyio.Event()

    @app.get("/test-only/interleave")
    async def interleave() -> dict[str, str]:
        nonlocal arrived
        before = str(current_request_id())
        arrived += 1
        if arrived == count:
            all_arrived.set()
        await all_arrived.wait()  # every request is in flight before any returns
        return {"before": before, "after": str(current_request_id())}

    supplied = [f"00000000-0000-4000-8000-{index:012d}" for index in range(count)]
    results: dict[str, httpx2.Response] = {}
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:

        async def call(request_id: str) -> None:
            results[request_id] = await client.get(
                "/test-only/interleave", headers={"X-Request-ID": request_id}
            )

        async with anyio.create_task_group() as group:
            for request_id in supplied:
                group.start_soon(call, request_id)

    for request_id, response in results.items():
        assert response.headers["X-Request-ID"] == request_id
        assert response.json() == {"before": request_id, "after": request_id}
