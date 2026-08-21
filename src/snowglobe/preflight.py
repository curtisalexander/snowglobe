"""Operator validation for the fixed local Snowflake profile."""

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from snowglobe.configuration import (
    build_connector_arguments,
    load_snowflake_profile,
    load_snowglobe_profile,
)
from snowglobe.snowflake import SnowflakeConnect, request_cursor
from snowglobe.sql_policy import SnowflakeSqlPolicy


def run_preflight(
    connections_path: Path,
    snowglobe_config_path: Path,
    profile_name: str,
    *,
    check_connection: bool = False,
    connect: SnowflakeConnect | None = None,
    progress: Callable[[str], None] | None = None,
) -> None:
    """Validate local configuration and optionally open one result-free connection."""

    if progress is not None:
        progress("Checking Snowflake connection profile...")
    connection = load_snowflake_profile(connections_path, profile_name)

    if progress is not None:
        progress("Checking Snowglobe policy profile and allowed views...")
    snowglobe_profile = load_snowglobe_profile(snowglobe_config_path, profile_name)
    SnowflakeSqlPolicy.from_view_names(snowglobe_profile.allowed_views)

    if progress is not None:
        progress("Checking RSA private key...")
    arguments = build_connector_arguments(connection)

    if check_connection:
        if progress is not None:
            progress(
                "Connecting to Snowflake and opening a cursor without executing SQL "
                "(30-second login timeout; an in-flight socket operation may take longer)..."
            )
        with request_cursor(arguments, connect=connect):
            pass
        if progress is not None:
            progress("Snowflake connection and cursor check passed.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a local Snowglobe profile.")
    parser.add_argument("--connections", type=Path, default=Path("connections.toml"))
    parser.add_argument("--snowglobe-config", type=Path, default=Path("snowglobe.toml"))
    parser.add_argument("--profile", default="default")
    parser.add_argument(
        "--connect",
        action="store_true",
        help="also open and close one Snowflake connection without executing SQL",
    )
    arguments = parser.parse_args(argv)

    try:
        run_preflight(
            arguments.connections,
            arguments.snowglobe_config,
            arguments.profile,
            check_connection=arguments.connect,
            progress=lambda message: print(message, flush=True),
        )
    except Exception as error:
        print(f"Snowglobe preflight failed: {error}", file=sys.stderr)
        return 1

    print("Snowglobe preflight passed.")
    return 0
