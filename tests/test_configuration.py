from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from snowglobe import secure_file
from snowglobe.configuration import ConfigurationError, build_connector_arguments, load_profile

VALID_CONFIG = """\
schema_version = 1

[connections.default]
account = "organization-account"
user = "SNOWGLOBE_SERVICE_USER"
authenticator = "SNOWFLAKE_JWT"
private_key_path = "~/snowglobe-key.p8"
database = "GOVERNED_DATABASE"
warehouse = "SNOWGLOBE_WAREHOUSE"
role = "SNOWGLOBE_READER"
allowed_views = ["GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW"]
"""


def test_loads_exact_profile(tmp_path: Path) -> None:
    path = tmp_path / "connections.toml"
    path.write_text(VALID_CONFIG, encoding="utf-8")
    path.chmod(0o600)

    profile = load_profile(path, "default")

    assert profile.database == "GOVERNED_DATABASE"
    assert profile.allowed_views == ("GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW",)
    assert profile.private_key_path == Path.home() / "snowglobe-key.p8"


def test_builds_only_explicit_connector_arguments(tmp_path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "snowflake-key.p8"
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    config_path = tmp_path / "connections.toml"
    config_path.write_text(
        VALID_CONFIG.replace("~/snowglobe-key.p8", str(key_path)), encoding="utf-8"
    )
    config_path.chmod(0o600)

    arguments = build_connector_arguments(load_profile(config_path, "default"))

    assert set(arguments) == {
        "account",
        "user",
        "authenticator",
        "private_key",
        "database",
        "warehouse",
        "role",
        "client_prefetch_threads",
        "login_timeout",
        "network_timeout",
        "socket_timeout",
        "session_parameters",
    }
    assert arguments == {
        "account": "organization-account",
        "user": "SNOWGLOBE_SERVICE_USER",
        "authenticator": "SNOWFLAKE_JWT",
        "private_key": key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
        "database": "GOVERNED_DATABASE",
        "warehouse": "SNOWGLOBE_WAREHOUSE",
        "role": "SNOWGLOBE_READER",
        "client_prefetch_threads": 1,
        "login_timeout": 30,
        "network_timeout": 60,
        "socket_timeout": 15,
        "session_parameters": {
            "ABORT_DETACHED_QUERY": True,
            "STATEMENT_QUEUED_TIMEOUT_IN_SECONDS": 15,
            "STATEMENT_TIMEOUT_IN_SECONDS": 60,
        },
    }


@pytest.mark.parametrize(
    "config",
    [
        VALID_CONFIG.replace("schema_version = 1", "schema_version = 2"),
        VALID_CONFIG.replace("role =", 'unexpected = "value"\nrole ='),
        VALID_CONFIG.replace("database =", "db ="),
        VALID_CONFIG.replace(
            'authenticator = "SNOWFLAKE_JWT"', 'authenticator = "externalbrowser"'
        ),
        VALID_CONFIG.replace('warehouse = "SNOWGLOBE_WAREHOUSE"\n', ""),
        VALID_CONFIG.replace(
            'allowed_views = ["GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW"]',
            'allowed_views = "GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW"',
        ),
        VALID_CONFIG.replace(
            'allowed_views = ["GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW"]',
            "allowed_views = []",
        ),
    ],
)
def test_rejects_invalid_configuration_without_detail(tmp_path: Path, config: str) -> None:
    path = tmp_path / "sensitive-name.toml"
    path.write_text(config, encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(ConfigurationError) as caught:
        load_profile(path, "default")

    assert str(caught.value) == ""


@pytest.mark.parametrize("mode", [0o200, 0o601, 0o640, 0o700])
def test_rejects_unsafe_configuration_permissions(tmp_path: Path, mode: int) -> None:
    path = tmp_path / "sensitive-name.toml"
    path.write_text(VALID_CONFIG, encoding="utf-8")
    path.chmod(mode)

    with pytest.raises(ConfigurationError) as caught:
        load_profile(path, "default")

    assert str(caught.value) == ""


def test_rejects_configuration_not_owned_by_current_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "sensitive-name.toml"
    path.write_text(VALID_CONFIG, encoding="utf-8")
    path.chmod(0o600)
    monkeypatch.setattr(secure_file.os, "geteuid", lambda: path.stat().st_uid + 1)

    with pytest.raises(ConfigurationError) as caught:
        load_profile(path, "default")

    assert str(caught.value) == ""


def test_rejects_configuration_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.toml"
    target.write_text(VALID_CONFIG, encoding="utf-8")
    target.chmod(0o600)
    path = tmp_path / "sensitive-name.toml"
    path.symlink_to(target)

    with pytest.raises(ConfigurationError) as caught:
        load_profile(path, "default")

    assert str(caught.value) == ""
