"""Strict, analyst-owned Snowflake connection configuration."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snowglobe.mvp_limits import (
    MVP_LOGIN_TIMEOUT_SECONDS,
    MVP_NETWORK_TIMEOUT_SECONDS,
    MVP_QUEUED_TIMEOUT_SECONDS,
    MVP_SOCKET_TIMEOUT_SECONDS,
    MVP_STATEMENT_TIMEOUT_SECONDS,
)
from snowglobe.private_key import load_private_key

SCHEMA_VERSION = 1
SNOWGLOBE_ROOT_FIELDS = frozenset({"schema_version", "profiles"})
SNOWGLOBE_PROFILE_FIELDS = frozenset({"allowed_views"})
CONNECTION_FIELDS = frozenset(
    {
        "account",
        "user",
        "authenticator",
        "private_key_path",
        "database",
        "warehouse",
        "role",
    }
)


class ConfigurationError(Exception):
    """A local Snowglobe configuration failure."""


@dataclass(frozen=True, slots=True)
class SnowflakeProfile:
    account: str
    user: str
    authenticator: str
    private_key_path: Path
    database: str
    warehouse: str
    role: str


@dataclass(frozen=True, slots=True)
class SnowglobeProfile:
    allowed_views: tuple[str, ...]


def build_connector_arguments(profile: SnowflakeProfile) -> dict[str, object]:
    """Build the exact server-owned arguments accepted by the Snowflake connector."""

    return {
        "account": profile.account,
        "user": profile.user,
        "authenticator": profile.authenticator,
        "private_key": load_private_key(profile.private_key_path),
        "database": profile.database,
        "warehouse": profile.warehouse,
        "role": profile.role,
        "client_prefetch_threads": 1,
        "login_timeout": MVP_LOGIN_TIMEOUT_SECONDS,
        "network_timeout": MVP_NETWORK_TIMEOUT_SECONDS,
        "socket_timeout": MVP_SOCKET_TIMEOUT_SECONDS,
        "session_parameters": {
            "ABORT_DETACHED_QUERY": True,
            "STATEMENT_QUEUED_TIMEOUT_IN_SECONDS": MVP_QUEUED_TIMEOUT_SECONDS,
            "STATEMENT_TIMEOUT_IN_SECONDS": MVP_STATEMENT_TIMEOUT_SECONDS,
        },
    }


def load_snowflake_profile(path: Path, profile_name: str) -> SnowflakeProfile:
    """Load reviewed fields from one native Snowflake connection definition."""

    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
        profile = document[profile_name]
        if not isinstance(profile, dict):
            raise ConfigurationError("Snowflake profile must be a TOML table")
        values = {field: _required_string(profile[field]) for field in CONNECTION_FIELDS}
        if values["authenticator"] != "SNOWFLAKE_JWT":
            raise ConfigurationError("Snowflake profile must use SNOWFLAKE_JWT")
    except (
        KeyError,
        OSError,
        tomllib.TOMLDecodeError,
        UnicodeError,
        TypeError,
        ValueError,
    ) as error:
        raise ConfigurationError(
            f"could not load Snowflake profile {profile_name!r} from {path}: {error}"
        ) from error

    return SnowflakeProfile(
        account=values["account"],
        user=values["user"],
        authenticator=values["authenticator"],
        private_key_path=Path(values["private_key_path"]).expanduser(),
        database=values["database"],
        warehouse=values["warehouse"],
        role=values["role"],
    )


def load_snowglobe_profile(path: Path, profile_name: str) -> SnowglobeProfile:
    """Load one exact Snowglobe-owned SQL policy profile."""

    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
        _require_exact_fields(document, SNOWGLOBE_ROOT_FIELDS)
        if document["schema_version"] != SCHEMA_VERSION:
            raise ConfigurationError(f"snowglobe.toml requires schema_version {SCHEMA_VERSION}")
        profiles = document["profiles"]
        if not isinstance(profiles, dict):
            raise ConfigurationError("snowglobe.toml profiles must be a TOML table")
        profile = profiles[profile_name]
        if not isinstance(profile, dict):
            raise ConfigurationError("Snowglobe profile must be a TOML table")
        _require_exact_fields(profile, SNOWGLOBE_PROFILE_FIELDS)
        allowed_views = _required_string_list(profile["allowed_views"])
    except (
        KeyError,
        OSError,
        tomllib.TOMLDecodeError,
        UnicodeError,
        TypeError,
        ValueError,
    ) as error:
        raise ConfigurationError(
            f"could not load Snowglobe profile {profile_name!r} from {path}: {error}"
        ) from error

    return SnowglobeProfile(allowed_views=allowed_views)


def _require_exact_fields(value: dict[str, Any], expected: frozenset[str]) -> None:
    if set(value) != expected:
        raise ConfigurationError("Snowglobe configuration fields do not match the schema")


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError("configuration values must be non-empty strings")
    return value


def _required_string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigurationError("allowed_views must be a non-empty list")
    values = tuple(_required_string(item) for item in value)
    if len(set(values)) != len(values):
        raise ConfigurationError("allowed_views must not contain duplicates")
    return values
