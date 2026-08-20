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
from snowglobe.secure_file import SecureFileError, read_secure_file

SCHEMA_VERSION = 1
SNOWGLOBE_ROOT_FIELDS = frozenset({"schema_version", "profiles"})
SNOWGLOBE_PROFILE_FIELDS = frozenset({"allowed_views"})
CONNECTION_FIELDS = frozenset(
    {
        "account",
        "user",
        "authenticator",
        "private_key_file",
        "database",
        "warehouse",
        "role",
    }
)


class ConfigurationError(Exception):
    """A deliberately detail-free configuration failure."""


@dataclass(frozen=True, slots=True)
class SnowflakeProfile:
    account: str
    user: str
    authenticator: str
    private_key_file: Path
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
        "private_key": load_private_key(profile.private_key_file),
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
        document = tomllib.loads(read_secure_file(path).decode("utf-8"))
        profile = document[profile_name]
        if not isinstance(profile, dict):
            raise ConfigurationError
        values = {field: _required_string(profile[field]) for field in CONNECTION_FIELDS}
        if values["authenticator"] != "SNOWFLAKE_JWT":
            raise ConfigurationError
    except (
        KeyError,
        OSError,
        SecureFileError,
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
        private_key_file=Path(values["private_key_file"]).expanduser(),
        database=values["database"],
        warehouse=values["warehouse"],
        role=values["role"],
    )


def load_snowglobe_profile(path: Path, profile_name: str) -> SnowglobeProfile:
    """Load one exact Snowglobe-owned SQL policy profile."""

    try:
        document = tomllib.loads(read_secure_file(path).decode("utf-8"))
        _require_exact_fields(document, SNOWGLOBE_ROOT_FIELDS)
        if document["schema_version"] != SCHEMA_VERSION:
            raise ConfigurationError
        profiles = document["profiles"]
        if not isinstance(profiles, dict):
            raise ConfigurationError
        profile = profiles[profile_name]
        if not isinstance(profile, dict):
            raise ConfigurationError
        _require_exact_fields(profile, SNOWGLOBE_PROFILE_FIELDS)
        allowed_views = _required_string_list(profile["allowed_views"])
    except (
        KeyError,
        OSError,
        SecureFileError,
        tomllib.TOMLDecodeError,
        UnicodeError,
        TypeError,
        ValueError,
    ) as error:
        raise ConfigurationError from error

    return SnowglobeProfile(allowed_views=allowed_views)


def _require_exact_fields(value: dict[str, Any], expected: frozenset[str]) -> None:
    if set(value) != expected:
        raise ConfigurationError


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError
    return value


def _required_string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigurationError
    values = tuple(_required_string(item) for item in value)
    if len(set(values)) != len(values):
        raise ConfigurationError
    return values
