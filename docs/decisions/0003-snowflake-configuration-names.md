# ADR 0003: Use Snowflake connector names in `connections.toml`

- **Status:** Superseded by [ADR 0016](0016-separate-snowflake-and-snowglobe-configuration.md)
- **Date:** August 18, 2026

## Context

The initial configuration sketch called the default Snowflake database `db` and mapped it to the connector's `database` argument. That alias adds translation without improving the operator-facing contract.

## Decision

Use `database` directly in `connections.toml`:

```toml
[connections.default]
account = "organization-account"
user = "SNOWGLOBE_SERVICE_USER"
authenticator = "SNOWFLAKE_JWT"
private_key_path = "/run/secrets/snowglobe_snowflake_key.p8"
database = "GOVERNED_DATABASE"
warehouse = "SNOWGLOBE_WAREHOUSE"
role = "SNOWGLOBE_READER"
```

The schema contains no `db` alias. The strict loader rejects `db` as an unknown field and passes `database` directly to `snowflake.connector.connect(database=...)` when connection construction is implemented.

## Consequences

- Configuration matches the Snowflake connector vocabulary.
- Documentation, tests, and operator examples have no translation layer to explain.
- Any pre-release local configuration using `db` must be changed to `database`; no compatibility alias or migration period is provided because Snowglobe has not shipped.
