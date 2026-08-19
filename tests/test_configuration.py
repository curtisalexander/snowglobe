from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

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
"""


def test_loads_exact_profile(tmp_path: Path) -> None:
    path = tmp_path / "connections.toml"
    path.write_text(VALID_CONFIG, encoding="utf-8")

    profile = load_profile(path, "default")

    assert profile.database == "GOVERNED_DATABASE"
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
    config_path = tmp_path / "connections.toml"
    config_path.write_text(
        VALID_CONFIG.replace("~/snowglobe-key.p8", str(key_path)), encoding="utf-8"
    )

    arguments = build_connector_arguments(load_profile(config_path, "default"))

    assert set(arguments) == {
        "account",
        "user",
        "authenticator",
        "private_key",
        "database",
        "warehouse",
        "role",
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
    ],
)
def test_rejects_invalid_configuration_without_detail(tmp_path: Path, config: str) -> None:
    path = tmp_path / "sensitive-name.toml"
    path.write_text(config, encoding="utf-8")

    with pytest.raises(ConfigurationError) as caught:
        load_profile(path, "default")

    assert str(caught.value) == ""
