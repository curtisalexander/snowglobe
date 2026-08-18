from pathlib import Path

import pytest

from snowglobe.configuration import ConfigurationError, load_profile

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
