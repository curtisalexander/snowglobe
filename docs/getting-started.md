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

Install Python 3.12, `uv`, Node.js 22.19 or newer, and npm. From a fresh clone:

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
connector needed to run the MCP server. Install the locked packages for the local
viewer separately:

```bash
npm ci
```

The setup command does not install Python development tools, test dependencies, the Pi
integration, Node.js, or npm itself. Repository contributors should instead follow the
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
The [governed SQL policy](sql-policy.md) explains which analytical query shapes are
accepted and how every direct external relation is checked.

## 3. Create the private profiles

Use your existing native Snowflake `connections.toml`, or copy
`connections.example.toml` to a private path outside the repository and replace every
placeholder:

```toml
[default]
account = "your-organization-your-account"
user = "SNOWGLOBE_TEST_USER"
authenticator = "SNOWFLAKE_JWT"
private_key_path = "/absolute/private/path/snowglobe-test-key.p8"
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
- `private_key_path` must be an absolute path to an unencrypted PEM or DER RSA key;
- `allowed_views` must be non-empty and contain exact, fully qualified
  `DATABASE.SCHEMA.VIEW` names; and
- missing Snowflake fields and missing, duplicate, or unknown Snowglobe policy fields
  are rejected.

The same profile name selects the Snowflake connection and Snowglobe policy. The role,
warehouse, database, authenticator, key path, and allowlist are launcher-owned. Never
put them in a prompt or MCP tool arguments.

Keep all three files untracked and manage them like your other local credentials.
Snowglobe reads the paths you supply and does not inspect file ownership or permissions.

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

The command reports each local check as it starts. These checks should finish almost
immediately. Successful output ends with `Snowglobe preflight passed.` A failure
includes the local path or configuration detail needed to fix it. Then open and close
one cursor without executing SQL:

```bash
uv run --locked --no-dev --extra snowflake snowglobe-preflight \
  --connections /absolute/private/path/connections.toml \
  --snowglobe-config /absolute/private/path/snowglobe.toml \
  --profile default \
  --connect
```

The connected check reports when it starts waiting for Snowflake. It normally finishes
within a few seconds. Login retries stop after 30 seconds, but the connector documents
that an in-flight socket operation can overrun that budget, so wall-clock time can be
longer. If it remains at that step for about a minute, interrupt it and check network,
DNS, account, and authentication settings before retrying.

This check confirms that the configured identity can authenticate and that the runtime
can create and close a cursor with the configured role, warehouse, and database. It
does not execute SQL or test whether every allowed view is readable. Verify separately
that Snowflake selected the expected context and recorded no statement. Stop if it
differs.

## 5. Start Snowglobe and the viewer

In the first terminal, run the one broker-owning process:

```bash
uv run --locked --no-dev --extra snowflake snowglobe-local \
  --connections /absolute/private/path/connections.toml \
  --snowglobe-config /absolute/private/path/snowglobe.toml \
  --profile default
```

Startup validates the local profiles, policy, and RSA key but does not connect to
Snowflake. Those checks should finish almost immediately. The command then starts the
loopback server and deliberately remains running in the foreground until you stop it
with `Ctrl-C`; this is not a hung startup. Wait for Uvicorn to report that application
startup is complete before continuing.

Keep that terminal running. It owns the in-memory broker that correlates MCP requests
with viewer results. Restarting or stopping it discards all request IDs and results
from that session.

In a second terminal, from the same repository checkout, start the loopback-only web
viewer:

```bash
npm run dev
```

Vite prints the viewer URL, normally `http://127.0.0.1:5173/`. Open the exact URL it
prints in your local browser; the port may differ if 5173 is already in use. Keep this
second process running while inspecting results. Vite proxies the viewer's `/v1`
requests to the broker-owning runtime on port 8000.

Confirm runtime health:

```bash
curl --fail --silent http://127.0.0.1:8000/healthz
```

On Windows PowerShell, use
`Invoke-RestMethod http://127.0.0.1:8000/healthz`.

The MCP endpoint is `http://127.0.0.1:8000/mcp`. Keep the process and MCP client on the
same local machine. Do not use VS Code Remote SSH, a dev container, a proxy, a tunnel,
port forwarding, or a non-loopback bind for the connected MVP. The viewer URL is for
the analyst's browser; do not ask the agent to open it or grant the agent browser,
screenshot, shell, or direct HTTP access for this experiment.

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
> Return the submission receipt, including the governed SQL, poll the request with
> Snowglobe until it is terminal, and report the lifecycle receipt.

No SQL file is required: the agent writes the `sql` tool argument from this request.
Snowglobe governs and regenerates that SQL rather than generating SQL from natural
language itself. The accepted submission receipt returns the request ID and exact
regenerated SQL being attempted, including the enforced row cap. Immediately before the
connector call, the `snowglobe-local` terminal prints the same pair. Treat model
transcripts and terminal captures as sensitive when SQL contains literals.

Expected agent-visible behavior:

1. submission returns only `status`, `request_id`, `reason_code`, and `governed_sql`;
2. status polling returns only `request_id` and `status`; and
3. a successful request eventually reaches `complete` without rows, schema, counts,
   timing, errors, Snowflake identifiers, or a result URL entering the conversation.

For this experiment, enable Snowglobe's MCP tools without separately enabling browser,
screenshot, shell, or direct HTTP tools. Those capabilities are controlled by the agent
host and are not granted by Snowglobe's MCP.

## 9. Open the result in the viewer

After the lifecycle receipt reaches `complete`:

1. Open the Vite URL printed by `npm run dev` in your local browser.
2. Find the request under **Recent requests**. The list refreshes automatically, or you
   can choose **Refresh**.
3. If it is not in the list, paste the exact opaque `request_id` into **Open a request
   ID returned by MCP**, then choose **Find request**.
4. When the request shows `complete` and the in-memory workspace is ready, choose
   **Open result**.
5. Inspect the bounded table under **Result preview**. Choose **Close result**, reload
   the page, or close the tab when finished to destroy that browser worker and its
   in-memory DuckDB data.

The viewer can open only a `complete`, unexpired result. If a request is still
`pending`, wait for completion; the **Open result** button remains disabled. A
`failed`, `cancelled`, or `expired` request has no result to open. Results expire at the
requested TTL (at most five minutes), so open the result promptly. If the viewer says
the request is unavailable, verify that both processes are still running and that the
request came from the current `snowglobe-local` session; request state is not restored
after a runtime restart.

The `request_id` is only a correlator. Do not append it to the viewer URL. Snowglobe
intentionally uses one fixed local viewer page where the analyst selects or pastes the
ID.

## 10. Finish the smoke test

Close the viewer tab, then stop Vite with `Ctrl-C` in its terminal. Stop
`snowglobe-local` with `Ctrl-C` in the first terminal. Confirm with the administrator
that no test query is running and the dedicated warehouse has auto-suspended. This
guide tests the governed MCP submission and lifecycle surface plus one local viewer
result; it does not test the Pi adapter or the complete connected failure matrix. Use
the [constrained MVP runbook](constrained-mvp-runbook.md) when running the broader
end-to-end product campaign.
