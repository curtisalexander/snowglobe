import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from snowglobe.preflight import main, run_preflight


class FakeCursor:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def cancel(self) -> None:
        self._events.append("cursor.cancel")

    def close(self) -> None:
        self._events.append("cursor.close")


class FakeConnection:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def cursor(self) -> FakeCursor:
        self._events.append("connection.cursor")
        return FakeCursor(self._events)

    def close(self) -> None:
        self._events.append("connection.close")


def write_profile(tmp_path: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "key.p8"
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    connections_path = tmp_path / "connections.toml"
    connections_path.write_text(
        f"""\
[default]
account = "organization-account"
user = "SNOWGLOBE_SERVICE_USER"
authenticator = "SNOWFLAKE_JWT"
private_key_path = {json.dumps(str(key_path))}
database = "GOVERNED_DATABASE"
warehouse = "SNOWGLOBE_WAREHOUSE"
role = "SNOWGLOBE_READER"
""",
        encoding="utf-8",
    )
    snowglobe_path = tmp_path / "snowglobe.toml"
    snowglobe_path.write_text(
        """\
schema_version = 1

[profiles.default]
allowed_views = ["GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW"]
""",
        encoding="utf-8",
    )
    return connections_path, snowglobe_path


def test_local_preflight_does_not_connect(tmp_path: Path) -> None:
    connections_path, snowglobe_path = write_profile(tmp_path)

    def unexpected_connect(**_arguments: object) -> FakeConnection:
        raise AssertionError("local preflight must not connect")

    run_preflight(connections_path, snowglobe_path, "default", connect=unexpected_connect)


def test_connected_preflight_opens_no_query(tmp_path: Path) -> None:
    connections_path, snowglobe_path = write_profile(tmp_path)
    events: list[str] = []
    progress: list[str] = []

    def connect(**arguments: object) -> FakeConnection:
        assert arguments["role"] == "SNOWGLOBE_READER"
        events.append("connect")
        return FakeConnection(events)

    run_preflight(
        connections_path,
        snowglobe_path,
        "default",
        check_connection=True,
        connect=connect,
        progress=progress.append,
    )

    assert events == ["connect", "connection.cursor", "cursor.close", "connection.close"]
    assert progress == [
        "Checking Snowflake connection profile...",
        "Checking Snowglobe policy profile and allowed views...",
        "Checking RSA private key...",
        (
            "Connecting to Snowflake and opening a cursor without executing SQL "
            "(30-second login timeout; an in-flight socket operation may take longer)..."
        ),
        "Snowflake connection and cursor check passed.",
    ]


def test_cli_reports_a_useful_local_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canary = "PREFLIGHT_SECRET_CANARY"
    missing_path = tmp_path / canary

    assert main(["--connections", str(missing_path)]) == 1

    captured = capsys.readouterr()
    assert captured.out == "Checking Snowflake connection profile...\n"
    assert captured.err.startswith("Snowglobe preflight failed:")
    assert canary in captured.err


def test_cli_reports_value_free_success(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    connections_path, snowglobe_path = write_profile(tmp_path)

    assert (
        main(
            [
                "--connections",
                str(connections_path),
                "--snowglobe-config",
                str(snowglobe_path),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert captured.out == (
        "Checking Snowflake connection profile...\n"
        "Checking Snowglobe policy profile and allowed views...\n"
        "Checking RSA private key...\n"
        "Snowglobe preflight passed.\n"
    )
    assert captured.err == ""
