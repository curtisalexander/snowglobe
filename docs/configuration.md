# Snowflake configuration

Snowglobe's Snowflake execution service reads an operator-owned `connections.toml`. This file is a server configuration boundary: it must not be available to the coding-agent environment, SPA, browser, MCP responses, or ordinary logs.

Use [`../connections.example.toml`](../connections.example.toml) as the starting point:

```toml
schema_version = 1

[connections.default]
account = "organization-account"
user = "SNOWGLOBE_SERVICE_USER"
authenticator = "SNOWFLAKE_JWT"
private_key_path = "/run/secrets/snowglobe_snowflake_key.p8"
database = "GOVERNED_DATABASE"
warehouse = "SNOWGLOBE_WAREHOUSE"
role = "SNOWGLOBE_READER"
```

## Initial contract

| Field | Meaning |
|---|---|
| `account` | Snowflake account identifier |
| `user` | Dedicated Snowglobe execution user |
| `authenticator` | Must be `SNOWFLAKE_JWT` in the initial implementation |
| `private_key_path` | Server-local PEM or DER private key; the key itself never belongs in TOML |
| `database` | Approved default database; passed directly to Snowflake connector parameter `database` |
| `warehouse` | Dedicated bounded Snowglobe warehouse |
| `role` | Least-privileged read role; never overridable by MCP input |

The current loader rejects missing or unknown fields and selects a named profile supplied by server deployment code, not tool input. Database, warehouse, role, authenticator, key path, and profile name are therefore operator policy—not agent-controlled query parameters.

The current private-key loader:

1. reads the expanded server-local path from the validated profile;
2. reads PEM or DER key material;
3. deserializes it with `cryptography`;
4. converts it in memory to unencrypted PKCS#8 DER expected by `snowflake.connector.connect`; and
5. avoids logging, tracing, serializing, or returning the path or key bytes.

Config/key ownership and permission enforcement remains a Milestone 0 task because local files and container secret mounts require different policies. The present loader verifies readability but does not yet enforce a permission mode.

Encrypted-key passphrases are intentionally not part of this first file contract. If needed, they must come from a secret manager or process secret—not a committed configuration file.

## File handling

- The real `connections.toml` is ignored by Git.
- Common private-key files (`*.pem`, `*.key`, and `*.p8`) are ignored, but deployment policy must protect key material regardless of extension.
- Prefer an absolute key path backed by a mounted secret with owner-only permissions.
- Do not place this configuration in an agent workspace or browser-served directory.
- Do not add a CLI or MCP tool that prints the resolved profile.

The configured Snowflake service identity does not replace human authorization. Snowglobe must bind every request to the authenticated human, enforce ownership in the Result API, and retain that opaque human association in its audit trail. Delegated per-user Snowflake identity remains a production evaluation item where row-access or masking policies depend on the actual user.
