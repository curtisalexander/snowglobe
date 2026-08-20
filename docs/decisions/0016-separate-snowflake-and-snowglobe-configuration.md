# ADR 0016: Separate Snowflake connections from Snowglobe policy

- **Status:** Accepted
- **Date:** August 20, 2026
- **Supersedes:** ADR 0003 and the configuration ownership portion of ADR 0010

## Context

Snowglobe's initial `connections.toml` was not a native Snowflake connections file. It
wrapped profiles under `[connections.<name>]`, used `private_key_path`, and added the
Snowglobe-only `schema_version` and `allowed_views` fields. An analyst with an existing
Snowflake `connections.toml` therefore had to maintain a second, incompatible version
of the same connection.

Connection credentials and SQL authorization policy also have different owners and
schemas. Mixing them makes a standard Snowflake file application-specific and obscures
which values are sent to the connector.

## Decision

- Consume native Snowflake `connections.toml` profiles from top-level tables such as
  `[default]`, including the native `private_key_file` name.
- Keep `schema_version` and per-profile `allowed_views` in a separate, strict
  Snowglobe-owned `snowglobe.toml`.
- Select the same profile name from both files.
- Permit other profiles and native connector fields in `connections.toml`, but read
  and forward only Snowglobe's explicit connection allowlist. Continue to require the
  fixed key-pair authenticator and execution context.
- Require both files before enabling execution. Validate both with the existing secure
  regular-file, ownership, permission, and no-link-or-reparse-point checks on POSIX and
  native Windows.

## Consequences

- An existing native Snowflake connections file can be used without Snowglobe fields.
- Snowflake's optional `schema` connection field can remain but is not forwarded;
  external relations still require fully qualified names authorized by Snowglobe.
- Operators pass `--connections` and `--snowglobe-config` explicitly. Supplying only
  one fails closed.
- Snowglobe policy remains versioned and schema-closed without claiming ownership of
  Snowflake's file format.
