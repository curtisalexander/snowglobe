# Snowflake configuration

Snowglobe reads an analyst-owned local `connections.toml`. This file is a process configuration boundary: it must not be available to the SPA, browser, MCP responses, or ordinary logs. If the coding agent can read all files owned by the analyst, filesystem secrecy from that agent is not a product guarantee; use operating-system or secret-manager controls when that distinction matters.

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
allowed_views = ["GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW"]
```

## MVP contract

| Field | Meaning |
|---|---|
| `account` | Snowflake account identifier |
| `user` | Dedicated Snowglobe execution user |
| `authenticator` | Must be `SNOWFLAKE_JWT` in the initial implementation |
| `private_key_path` | Server-local PEM or DER private key; the key itself never belongs in TOML |
| `database` | Approved default database; passed directly to Snowflake connector parameter `database` |
| `warehouse` | Dedicated bounded Snowglobe warehouse |
| `role` | Least-privileged read role; never overridable by MCP input |
| `allowed_views` | Non-empty exact list of fully qualified `DATABASE.SCHEMA.VIEW` relations accepted by SQL policy |

The current loader rejects missing or unknown fields and selects a named profile supplied by local startup code, not tool input. Database, warehouse, role, authenticator, key path, and profile name are therefore analyst configuration—not agent-controlled query parameters.

The connector-argument builder copies only reviewed driver parameters; it does not
forward the TOML document, `allowed_views`, or the key path. It supplies:

- `account`, `user`, `authenticator`, in-memory `private_key`, `database`, `warehouse`,
  and `role` from the selected profile;
- one client prefetch thread and fixed login, network, and socket timeouts; and
- fixed `ABORT_DETACHED_QUERY`, statement-timeout, and queue-timeout session
  parameters.

While building those arguments, the private-key loader:

1. reads the expanded server-local path from the validated profile;
2. reads PEM or DER key material;
3. deserializes it with `cryptography`;
4. converts it in memory to unencrypted PKCS#8 DER expected by `snowflake.connector.connect`; and
5. avoids logging, tracing, serializing, or returning the path or key bytes.

The profile and key must each be a user-readable regular file owned by the current
user and must not grant access to unprivileged other users. On POSIX, owner mode `0400`
or `0600` is accepted and Snowglobe opens with `O_NOFOLLOW`. On native Windows,
Snowglobe opens the path with `FILE_FLAG_OPEN_REPARSE_POINT`, rejects every reparse
point, checks that the owner SID matches the current process-token user, and rejects
allow ACL entries for principals other than that user, Local System, or Administrators.
Those privileged principals are equivalent to POSIX root and are outside Snowglobe's
host-isolation claim.

Native Windows support requires a local NTFS volume. FAT, exFAT, incompatible network
shares, and reparse-point paths fail closed. See
[ADR 0015](decisions/0015-native-windows-credential-files.md).

Encrypted-key passphrases are intentionally not part of this first file contract. If needed, they must come from a secret manager or process secret—not a committed configuration file.

## File handling

- The real `connections.toml` is ignored by Git.
- Common private-key files (`*.pem`, `*.key`, and `*.p8`) are ignored, but deployment policy must protect key material regardless of extension.
- Keep both files outside the repository when possible. Set each to mode `0600` on
  POSIX or remove inherited ACL access with the documented `icacls` command on Windows.
- Use an absolute key path. Secret mounts are accepted only when they appear as an
  owner-only regular file and satisfy the same checks.
- Do not place this configuration in an agent workspace or browser-served directory.
- Do not add a CLI or MCP tool that prints the resolved profile.

The configured Snowflake identity is the analyst's local execution identity. Its role and Snowflake policies are the independent data-access boundary. Snowglobe does not add viewer accounts or a second human authorization layer.
