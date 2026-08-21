# Getting started with Snowglobe

This is the clone-to-first-query guide for Snowglobe's connected MVP. The current
scope is a dedicated non-production Snowflake environment containing only
non-sensitive synthetic canaries. Do not use production credentials, production data,
sensitive data, or a broad analyst role.

For the complete security and failure matrix, use the
[constrained MVP runbook](constrained-mvp-runbook.md). `SECURITY.md` remains
authoritative.

## 1. Prerequisites and installation

Use Linux, macOS, or native Windows 10/11. Snowglobe relies on the analyst and
operating system to manage file access.

Install Python 3.12 and `uv`. From a fresh clone:

```bash
git clone https://github.com/curtisalexander/snowglobe.git
cd snowglobe
./scripts/setup-mcp.sh
```

On Windows PowerShell:

```powershell
git clone https://github.com/curtisalexander/snowglobe.git
Set-Location snowglobe
./scripts/setup-mcp.ps1
```

The remaining multi-line `bash` examples use `\` for continuation. In PowerShell,
remove the backslashes and run the same arguments on one line; Windows paths may use
forward slashes in Snowglobe arguments and TOML.

The setup command installs only the locked Python runtime dependencies and Snowflake
connector needed to run the MCP server. It does not install development tools, test
dependencies, Node.js, npm packages, the Pi integration, or the viewer development
server. Repository contributors should instead follow the
[developer setup](developer-guide.md#developer-setup-and-daily-loop).

## 2. Prepare a constrained Snowflake environment

Ask a Snowflake administrator to provision or verify:

- a dedicated key-pair-authenticated test user whose default and only assigned role is
  the dedicated Snowglobe test role;
- no relevant object access through Snowflake's unavoidable `PUBLIC` role;
- a dedicated read-only role with usage only on the intended test warehouse,
  database, and schema, plus select only on explicitly approved test views;
- a small dedicated warehouse with auto-suspend, auto-resume, and an active
  administrator-owned resource monitor; and
- non-sensitive synthetic views, beginning with one approved view containing no more
  than 50 rows, 32 columns, or 16 KiB in any variable-width cell.

Do not reuse a production user, production database, broad analyst role, password,
browser authenticator, or role capable of assuming broader privileges. Snowglobe's
current profile supports only `SNOWFLAKE_JWT` key-pair authentication. Follow
[Snowflake's key-pair authentication procedure](https://docs.snowflake.com/en/user-guide/key-pair-auth)
to assign the public key to the dedicated user; Snowglobe receives only the private-key
file path.

The full connected campaign needs the additional empty, multi-batch, overflow,
timeout, cancellation, and unapproved views in
[runbook section 2](constrained-mvp-runbook.md#2-administrator-owned-environment-setup).

## 3. Create the private profiles

Use your existing native Snowflake `connections.toml`, or copy
`connections.example.toml` to a private path outside the repository and replace every
placeholder:

```toml
[default]
account = "your-organization-your-account"
user = "SNOWGLOBE_TEST_USER"
authenticator = "SNOWFLAKE_JWT"
private_key_file = "/absolute/private/path/snowglobe-test-key.p8"
database = "YOUR_TEST_DATABASE"
warehouse = "YOUR_TEST_WAREHOUSE"
role = "YOUR_SNOWGLOBE_READER_ROLE"
```

Copy `snowglobe.example.toml` to a separate private path and configure Snowglobe's
query policy:

```toml
schema_version = 1

[profiles.default]
allowed_views = [
  "YOUR_TEST_DATABASE.YOUR_TEST_SCHEMA.YOUR_APPROVED_VIEW",
]
```

On Windows, TOML accepts a forward-slash path such as
`C:/Users/you/.snowglobe/snowglobe-test-key.p8` without backslash escaping.

Field rules:

- `account` is the identifier expected by the Snowflake Python connector;
- use `database`, never `db`;
- `private_key_file` must be an absolute path to an unencrypted PEM or DER RSA key;
- `allowed_views` must be non-empty and contain exact, fully qualified
  `DATABASE.SCHEMA.VIEW` names; and
- missing Snowflake fields and missing, duplicate, or unknown Snowglobe policy fields
  are rejected.

The same profile name selects the Snowflake connection and Snowglobe policy. The role,
warehouse, database, authenticator, key path, and allowlist are launcher-owned. Never
put them in a prompt or MCP tool arguments.

Keep all three files in an access-controlled location outside the repository and
agent-visible workspaces. Snowglobe does not inspect file ownership or permissions.

```bash
chmod 600 /absolute/private/path/connections.toml
chmod 600 /absolute/private/path/snowglobe.toml
chmod 600 /absolute/private/path/snowglobe-test-key.p8
```

See the [configuration reference](configuration.md) for the exact file contract and
handling guidance.

## 4. Run preflight

First validate the profile, key, and allowlist without connecting:

```bash
uv run --locked --no-dev --extra snowflake snowglobe-preflight \
  --connections /absolute/private/path/connections.toml \
  --snowglobe-config /absolute/private/path/snowglobe.toml \
  --profile default
```

The only successful output is `Snowglobe preflight passed.` Then, under the runbook's
constrained exception, open and close one cursor without executing SQL:

```bash
uv run --locked --no-dev --extra snowflake snowglobe-preflight \
  --connections /absolute/private/path/connections.toml \
  --snowglobe-config /absolute/private/path/snowglobe.toml \
  --profile default \
  --connect
```

Have the administrator verify independently that the login selected the expected user,
role, warehouse, and database and executed no statement. Stop if they differ.

## 5. Start Snowglobe

In the first terminal, run the one broker-owning process:

```bash
uv run --locked --no-dev --extra snowflake snowglobe-local \
  --connections /absolute/private/path/connections.toml \
  --snowglobe-config /absolute/private/path/snowglobe.toml \
  --profile default
```

Confirm runtime health:

```bash
curl --fail --silent http://127.0.0.1:8000/healthz
```

On Windows PowerShell, use
`Invoke-RestMethod http://127.0.0.1:8000/healthz`.

The MCP endpoint is `http://127.0.0.1:8000/mcp`. Keep the process and MCP client on the
same local machine. Do not use VS Code Remote SSH, a dev container, a proxy, a tunnel,
port forwarding, or a non-loopback bind for the connected MVP.

## 6. Configure one control adapter

Choose one native MCP client below. MCP configuration contains only Snowglobe's
loopback URL; it contains no Snowflake credential or connection setting. Restart or
reload a native client after configuring it.

### Amp

Create or update `.amp/settings.json` in the repository:

```json
{
  "amp.mcpServers": {
    "snowglobe": {
      "url": "http://127.0.0.1:8000/mcp",
      "includeTools": ["submit_read_query", "get_query_status"]
    }
  }
}
```

Start Amp from the repository and approve the workspace MCP server when prompted. Run
`amp mcp doctor` if it remains in `awaiting approval` or does not connect. See the
[Amp MCP manual](https://ampcode.com/manual#mcp).

### OpenAI Codex CLI or IDE extension

From the repository, register Snowglobe:

```bash
codex mcp add snowglobe --url http://127.0.0.1:8000/mcp
codex mcp list
```

Codex CLI and the Codex IDE extension share this configuration. Alternatively, add a
project-scoped `.codex/config.toml` in a trusted checkout:

```toml
[mcp_servers.snowglobe]
url = "http://127.0.0.1:8000/mcp"
enabled_tools = ["submit_read_query", "get_query_status"]
default_tools_approval_mode = "prompt"
```

Start a new Codex session and use `/mcp` to verify the server. See the
[Codex MCP documentation](https://developers.openai.com/codex/mcp).

### Claude Code

From the repository, add a private, project-local HTTP server:

```bash
claude mcp add --scope local --transport http \
  snowglobe http://127.0.0.1:8000/mcp
claude mcp list
```

Start a new Claude Code session and use `/mcp` to verify the connection and tools.
Local scope stores the setting privately for this checkout. To create a team-reviewed
project setting instead, use `--scope project`, which writes `.mcp.json`; do not place
Snowflake settings or credentials in that file. See the
[Claude Code MCP guide](https://code.claude.com/docs/en/mcp-quickstart).

### Continue.dev VS Code extension

Continue supports MCP only in **Agent mode**. In the repository, create
`.continue/mcpServers/snowglobe.yaml`:

```yaml
name: Snowglobe MCP
version: 0.0.1
schema: v1
mcpServers:
  - name: Snowglobe
    type: streamable-http
    url: http://127.0.0.1:8000/mcp
```

Reload the VS Code window, open Continue, switch to Agent mode, and confirm Snowglobe
appears in the available tools. Use a current Continue release; older releases did not
support Streamable HTTP. If your organization's Continue configuration or VS Code
policy blocks workspace MCP servers, an administrator must allow this exact loopback
endpoint. See [Continue's MCP guide](https://docs.continue.dev/customize/deep-dives/mcp).

Do not configure the same file as both YAML and JSON, and do not use the deprecated
SSE transport. Run the Continue extension and Snowglobe directly on the same local
machine rather than through a remote VS Code extension host.

## 7. Verify the control surface

Native MCP clients must see exactly:

- `submit_read_query(sql, requested_ttl)`
- `get_query_status(request_id)`

It must not advertise Snowglobe resources, prompts, result readers, cancellation
tools, or connection-setting inputs. If the runtime was started without both
configuration files, a
submission correctly returns `SERVICE_UNAVAILABLE`.

## 8. Run the first agent experiment

Replace the relation below with one exact fully qualified entry from the private
Snowglobe profile's `allowed_views`. Do not include canary values in the prompt or SQL;
they must originate in the administrator-approved view.

> Use Snowglobe to submit this governed read query:
> `SELECT * FROM YOUR_TEST_DATABASE.YOUR_TEST_SCHEMA.YOUR_APPROVED_VIEW`.
> Use a TTL of 300 seconds.
> Return the opaque submission receipt, poll the request with Snowglobe until it is
> terminal, and report only the lifecycle receipt.

Expected agent-visible behavior:

1. submission returns only `status`, `request_id`, and `reason_code`;
2. status polling returns only `request_id` and `status`; and
3. a successful request eventually reaches `complete` without rows, schema, counts,
   timing, errors, Snowflake identifiers, or a result URL entering the conversation.

For this experiment, enable Snowglobe's MCP tools without separately enabling browser,
screenshot, shell, or direct HTTP tools. Those capabilities are controlled by the agent
host and are not granted by Snowglobe's MCP.

## 9. Finish the MCP smoke test

Stop `snowglobe-local` with `Ctrl-C`. Confirm with the administrator that no test query
is running and the dedicated warehouse has auto-suspended. This guide tests only the
MCP server's governed submission and lifecycle surface; it does not install or test the
viewer, Pi adapter, or repository development toolchain. Use the
[constrained MVP runbook](constrained-mvp-runbook.md) only when running the broader
end-to-end product campaign.
