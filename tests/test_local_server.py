import pytest
from pytest import MonkeyPatch
from starlette.applications import Starlette
from starlette.testclient import TestClient

from snowglobe import local_server
from snowglobe.local_server import create_app
from snowglobe.mvp_limits import MVP_ARROW_LIMITS
from snowglobe.runtime import create_runtime


def test_local_server_shares_one_broker_between_mcp_and_viewer_routes() -> None:
    runtime = create_runtime()
    app = create_app(runtime)

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

    assert invocation["host"] == "127.0.0.1"
    assert invocation["port"] == 8000
    application = invocation["app"]
    assert isinstance(application, Starlette)
    assert application.state.broker is application.state.runtime.broker


def test_local_launcher_fails_closed_with_only_one_config_file(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unexpected_run(*_arguments: object, **_keywords: object) -> None:
        raise AssertionError("invalid configuration must not start the server")

    monkeypatch.setattr(local_server.uvicorn, "run", unexpected_run)

    assert local_server.main(["--connections", "connections.toml"]) == 1
    assert capsys.readouterr().err == (
        "Snowglobe startup failed: --connections and --snowglobe-config must be supplied together\n"
    )
