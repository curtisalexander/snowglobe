from starlette.testclient import TestClient

from snowglobe.result_api import app


def test_health_is_value_free_and_not_cached() -> None:
    response = TestClient(app).get("/healthz")

    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"
