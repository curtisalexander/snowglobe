# Snowflake and Snowglobe configuration

Snowglobe reads two analyst-owned local files with separate ownership:

- a native Snowflake `connections.toml` containing connection definitions; and
- a Snowglobe-owned `snowglobe.toml` containing versioned query policy.

Neither file may be available to the SPA, browser, MCP responses, or ordinary logs. If
the coding agent can read all files owned by the analyst, filesystem secrecy from that
agent is not a product guarantee; use operating-system or secret-manager controls when
that distinction matters.

## Native Snowflake connections

Use an existing native Snowflake `connections.toml`, or start from
[`../connections.example.toml`](../connections.example.toml):

```toml
[default]
account = "organization-account"
user = "SNOWGLOBE_SERVICE_USER"
authenticator = "SNOWFLAKE_JWT"
private_key_file = "/run/secrets/snowglobe_snowflake_key.p8"
database = "GOVERNED_DATABASE"
warehouse = "SNOWGLOBE_WAREHOUSE"
role = "SNOWGLOBE_READER"
```

Snowglobe selects the top-level connection named by `--profile`. The selected
connection must provide the seven fields shown above and must use `SNOWFLAKE_JWT`.
Other native connection definitions and connector fields, including Snowflake's
optional `schema` connection setting, may remain in the file. Snowglobe reads but does
not forward fields outside its explicit connector allowlist.

The connector-argument builder supplies only `account`, `user`, `authenticator`, an
in-memory `private_key`, `database`, `warehouse`, and `role`, plus fixed prefetch,
timeout, and session settings. Role, warehouse, database, authenticator, key path, and
profile name are analyst configuration—not agent-controlled query parameters.

## Snowglobe query policy

Copy [`../snowglobe.example.toml`](../snowglobe.example.toml) to an untracked private
path:

```toml
schema_version = 1

[profiles.default]
allowed_views = ["GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW"]
```

The Snowglobe profile name must match the selected Snowflake connection name.
`allowed_views` must be a non-empty, unique list of exact, fully qualified
`DATABASE.SCHEMA.VIEW` relations accepted by SQL policy. The Snowglobe file has a
closed, versioned schema; unknown or missing fields fail.

## Key and file handling

While building connector arguments, Snowglobe reads the selected profile's
`private_key_file`, deserializes an unencrypted PEM or DER RSA key, and converts it in
memory to the PKCS#8 DER bytes expected by `snowflake.connector.connect`. It does not
log, trace, serialize, or return the path or key bytes.

Snowglobe uses normal reads from the configured paths and trusts the analyst and
operating system to manage file access. Another local account permitted to access a
file can read or modify it without Snowglobe detecting that access. See
[ADR 0017](decisions/0017-minimal-model-context-boundary.md). Encrypted-key
passphrases are intentionally not part of the file contract.

- The real `connections.toml` and `snowglobe.toml` are ignored by Git.
- Common private-key files (`*.pem`, `*.key`, and `*.p8`) are ignored, but deployment
  policy must protect key material regardless of extension.
- Keep both configuration files and the key outside the repository when possible.
- Use absolute paths when invoking Snowglobe and for `private_key_file`.
- Do not place this configuration in an agent workspace or browser-served directory.
- Do not add a CLI or MCP tool that prints either resolved profile.

On POSIX:

```bash
chmod 600 /absolute/private/path/connections.toml
chmod 600 /absolute/private/path/snowglobe.toml
chmod 600 /absolute/private/path/snowglobe-key.p8
```

The configured Snowflake identity is the analyst's local execution identity. Its role
and Snowflake policies are the independent data-access boundary. Snowglobe does not add
viewer accounts or a second human authorization layer.
