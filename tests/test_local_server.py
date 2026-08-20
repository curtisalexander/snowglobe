from pytest import MonkeyPatch
from starlette.testclient import TestClient

from snowglobe import local_server
from snowglobe.local_server import create_app
from snowglobe.mvp_limits import MVP_ARROW_LIMITS
from snowglobe.runtime import runtime


def test_local_server_shares_one_broker_between_mcp_and_viewer_routes() -> None:
    app = create_app()

    assert app.state.runtime is runtime
    assert app.state.broker is runtime.broker
    assert app.state.admission_limits is MVP_ARROW_LIMITS
    response = TestClient(app).get("/v1/requests")
    assert response.status_code == 200
    assert "requests" in response.json()


def test_local_launcher_binds_only_to_loopback(monkeypatch: MonkeyPatch) -> None:
    invocation: dict[str, object] = {}

    def run(app: object, *, host: str, port: int) -> None:
        invocation.update(app=app, host=host, port=port)

    monkeypatch.setattr(local_server.uvicorn, "run", run)

    assert local_server.main([]) == 0

    assert invocation == {
        "app": local_server.app,
        "host": "127.0.0.1",
        "port": 8000,
    }
