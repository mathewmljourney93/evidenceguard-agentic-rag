from fastapi.testclient import TestClient

from evidenceguard_api.app import create_app


def test_healthz_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_create_app_returns_independent_instances() -> None:
    assert create_app() is not create_app()


def test_unknown_path_is_not_found() -> None:
    client = TestClient(create_app())

    assert client.get("/readyz").status_code == 404
