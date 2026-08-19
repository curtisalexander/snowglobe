"""Strict, analyst-owned Snowflake connection configuration."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
ROOT_FIELDS = frozenset({"schema_version", "connections"})
PROFILE_FIELDS = frozenset(
    {"account", "user", "authenticator", "private_key_path", "database", "warehouse", "role"}
)


class ConfigurationError(Exception):
    """A deliberately detail-free configuration failure."""


@dataclass(frozen=True, slots=True)
class SnowflakeProfile:
    account: str
    user: str
    authenticator: str
    private_key_path: Path
    database: str
    warehouse: str
    role: str


def load_profile(path: Path, profile_name: str) -> SnowflakeProfile:
    """Load one server-selected profile, rejecting unknown or malformed input."""

    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
        _require_exact_fields(document, ROOT_FIELDS)
        if document["schema_version"] != SCHEMA_VERSION:
            raise ConfigurationError

        connections = document["connections"]
        if not isinstance(connections, dict):
            raise ConfigurationError
        profile = connections[profile_name]
        if not isinstance(profile, dict):
            raise ConfigurationError
        _require_exact_fields(profile, PROFILE_FIELDS)
        values = {field: _required_string(profile[field]) for field in PROFILE_FIELDS}
        if values["authenticator"] != "SNOWFLAKE_JWT":
            raise ConfigurationError
    except (
        KeyError,
        OSError,
        tomllib.TOMLDecodeError,
        UnicodeError,
        TypeError,
        ValueError,
    ) as error:
        raise ConfigurationError from error

    return SnowflakeProfile(
        account=values["account"],
        user=values["user"],
        authenticator=values["authenticator"],
        private_key_path=Path(values["private_key_path"]).expanduser(),
        database=values["database"],
        warehouse=values["warehouse"],
        role=values["role"],
    )


def _require_exact_fields(value: dict[str, Any], expected: frozenset[str]) -> None:
    if set(value) != expected:
        raise ConfigurationError


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError
    return value
