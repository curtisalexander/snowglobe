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
ROOT_FIELDS = frozenset({"schema_version", "connections"})
PROFILE_FIELDS = frozenset(
    {
        "account",
        "user",
        "authenticator",
        "private_key_path",
        "database",
        "warehouse",
        "role",
        "allowed_views",
    }
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


def load_profile(path: Path, profile_name: str) -> SnowflakeProfile:
    """Load one server-selected profile, rejecting unknown or malformed input."""

    try:
        document = tomllib.loads(read_secure_file(path).decode("utf-8"))
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
        values = {
            field: _required_string(profile[field])
            for field in PROFILE_FIELDS
            if field != "allowed_views"
        }
        allowed_views = _required_string_list(profile["allowed_views"])
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
        private_key_path=Path(values["private_key_path"]).expanduser(),
        database=values["database"],
        warehouse=values["warehouse"],
        role=values["role"],
        allowed_views=allowed_views,
    )


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
