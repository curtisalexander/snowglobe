import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from snowglobe.configuration import (
    ConfigurationError,
    build_connector_arguments,
    load_snowflake_profile,
    load_snowglobe_profile,
)

VALID_CONNECTIONS = """\
[default]
account = "organization-account"
user = "SNOWGLOBE_SERVICE_USER"
authenticator = "SNOWFLAKE_JWT"
private_key_file = "~/snowglobe-key.p8"
database = "GOVERNED_DATABASE"
warehouse = "SNOWGLOBE_WAREHOUSE"
role = "SNOWGLOBE_READER"
schema = "GOVERNED_SCHEMA"

[another_connection]
account = "another-account"
"""

VALID_SNOWGLOBE_CONFIG = """\
schema_version = 1

[profiles.default]
allowed_views = ["GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW"]
"""


def write_secure(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o600)


def test_loads_native_snowflake_profile_and_separate_policy(tmp_path: Path) -> None:
    connections_path = tmp_path / "connections.toml"
    snowglobe_path = tmp_path / "snowglobe.toml"
    write_secure(connections_path, VALID_CONNECTIONS)
    write_secure(snowglobe_path, VALID_SNOWGLOBE_CONFIG)

    connection = load_snowflake_profile(connections_path, "default")
    snowglobe_profile = load_snowglobe_profile(snowglobe_path, "default")

    assert connection.database == "GOVERNED_DATABASE"
    assert connection.private_key_file == Path.home() / "snowglobe-key.p8"
    assert snowglobe_profile.allowed_views == ("GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW",)


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
    connections_path = tmp_path / "connections.toml"
    write_secure(
        connections_path,
        VALID_CONNECTIONS.replace('"~/snowglobe-key.p8"', json.dumps(str(key_path))),
    )

    arguments = build_connector_arguments(load_snowflake_profile(connections_path, "default"))

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
        VALID_CONNECTIONS.replace("database =", "db ="),
        VALID_CONNECTIONS.replace(
            'authenticator = "SNOWFLAKE_JWT"', 'authenticator = "externalbrowser"'
        ),
        VALID_CONNECTIONS.replace('warehouse = "SNOWGLOBE_WAREHOUSE"\n', ""),
    ],
)
def test_rejects_invalid_connection_without_detail(tmp_path: Path, config: str) -> None:
    path = tmp_path / "sensitive-name.toml"
    write_secure(path, config)

    with pytest.raises(ConfigurationError) as caught:
        load_snowflake_profile(path, "default")

    assert str(caught.value) == ""


@pytest.mark.parametrize(
    "config",
    [
        VALID_SNOWGLOBE_CONFIG.replace("schema_version = 1", "schema_version = 2"),
        VALID_SNOWGLOBE_CONFIG.replace("allowed_views =", 'unexpected = "value"\nallowed_views ='),
        VALID_SNOWGLOBE_CONFIG.replace(
            'allowed_views = ["GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW"]',
            'allowed_views = "GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW"',
        ),
        VALID_SNOWGLOBE_CONFIG.replace(
            'allowed_views = ["GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW"]',
            "allowed_views = []",
        ),
    ],
)
def test_rejects_invalid_snowglobe_config_without_detail(tmp_path: Path, config: str) -> None:
    path = tmp_path / "sensitive-name.toml"
    write_secure(path, config)

    with pytest.raises(ConfigurationError) as caught:
        load_snowglobe_profile(path, "default")

    assert str(caught.value) == ""
