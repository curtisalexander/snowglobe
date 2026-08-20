# Getting started with Snowglobe

This is the clone-to-first-query guide for Snowglobe's connected MVP. The current
scope is a dedicated non-production Snowflake environment containing only
non-sensitive synthetic canaries. Do not use production credentials, production data,
sensitive data, or a broad analyst role.

For the complete security and failure matrix, use the
[constrained MVP runbook](constrained-mvp-runbook.md). `SECURITY.md` remains
authoritative.

## 1. Prerequisites and installation

Use Linux, macOS, or native Windows 10/11. On Windows, keep the configuration and key
on a local NTFS volume; FAT, exFAT, incompatible network shares, and reparse-point
paths cannot provide the reviewed credential-file checks and fail closed.

Install Python 3.12, `uv`, Node.js 22.12 or newer, and npm. From a fresh clone:

```bash
git clone https://github.com/curtisalexander/snowglobe.git
cd snowglobe
./scripts/setup.sh
./scripts/check.sh
```

On Windows PowerShell:

```powershell
git clone https://github.com/curtisalexander/snowglobe.git
Set-Location snowglobe
./scripts/setup.ps1
./scripts/check.ps1
```

The remaining multi-line `bash` examples use `\` for continuation. In PowerShell,
remove the backslashes and run the same arguments on one line; Windows paths may use
forward slashes in Snowglobe arguments and TOML.

The setup command installs the locked Python dependencies, pinned Snowflake connector,
and locked viewer dependencies. The check command runs formatting, lint, Python and
TypeScript type checks, the backend and viewer test suites, and the production build.
It does not connect to Snowflake.

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

## 3. Create the private profile

Copy `connections.example.toml` to a private path outside the repository and replace
every placeholder:

```toml
schema_version = 1

[connections.default]
account = "your-organization-your-account"
user = "SNOWGLOBE_TEST_USER"
authenticator = "SNOWFLAKE_JWT"
private_key_path = "/absolute/private/path/snowglobe-test-key.p8"
database = "YOUR_TEST_DATABASE"
warehouse = "YOUR_TEST_WAREHOUSE"
role = "YOUR_SNOWGLOBE_READER_ROLE"
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
- missing, duplicate, or unknown fields are rejected.

The profile name, role, warehouse, database, authenticator, key path, and allowlist are
launcher-owned. Never put them in a prompt or MCP tool arguments.

Make both files owner-only regular files:

```bash
chmod 600 /absolute/private/path/connections.toml
chmod 600 /absolute/private/path/snowglobe-test-key.p8
```

On Windows, create them on local NTFS storage, then remove inherited access and grant
your current account read/write access. Run this from PowerShell after setting the two
paths:

```powershell
$config = "$env:USERPROFILE\.snowglobe\connections.toml"
$key = "$env:USERPROFILE\.snowglobe\snowglobe-test-key.p8"
$account = "$env:USERDOMAIN\$env:USERNAME"
icacls $config /inheritance:r /grant:r "${account}:(R,W)"
icacls $key /inheritance:r /grant:r "${account}:(R,W)"
```

Snowglobe verifies the owner SID and ACL on the opened file handle and rejects all
reparse points. Local System and Administrators remain privileged, like POSIX root.

See the [configuration reference](configuration.md) for the exact contract and file
checks.

## 4. Run preflight

First validate the profile, key, and allowlist without connecting:

```bash
uv run snowglobe-preflight \
  --config /absolute/private/path/connections.toml \
  --profile default
```

The only successful output is `Snowglobe preflight passed.` Then, under the runbook's
constrained exception, open and close one cursor without executing SQL:

```bash
uv run snowglobe-preflight \
  --config /absolute/private/path/connections.toml \
  --profile default \
  --connect
```

Have the administrator verify independently that the login selected the expected user,
role, warehouse, and database and executed no statement. Stop if they differ.

## 5. Start Snowglobe

In the first terminal, run the one broker-owning process:

```bash
uv run snowglobe-local \
  --config /absolute/private/path/connections.toml \
  --profile default
```

In a second terminal, start the loopback viewer:

```bash
npm run dev
```

Confirm runtime health:

```bash
curl --fail --silent http://127.0.0.1:8000/healthz
```

On Windows PowerShell, use
`Invoke-RestMethod http://127.0.0.1:8000/healthz`.

The MCP endpoint is `http://127.0.0.1:8000/mcp`. Vite prints the viewer URL, normally
`http://127.0.0.1:5173/`. Keep both processes and the MCP client on the same local
machine. Do not use VS Code Remote SSH, a dev container, a proxy, a tunnel, port
forwarding, or a non-loopback bind for the connected MVP.

## 6. Configure one control adapter

Choose one native MCP client below, or install the native Pi package. MCP configuration
contains only Snowglobe's loopback URL; it contains no Snowflake credential or
connection setting. Restart or reload a native client after configuring it.

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

### Pi

Pi does not support MCP, so Snowglobe provides a native Pi package. Install it directly
from the exact clean revision you reviewed:

```bash
test -z "$(git status --short)"
SNOWGLOBE_REF="$(git rev-parse HEAD)"
pi install "git:github.com/curtisalexander/snowglobe@${SNOWGLOBE_REF}"
pi list
```

On Windows PowerShell:

```powershell
if (git status --short) { throw "The checkout must be clean." }
$snowglobeRef = git rev-parse HEAD
pi install "git:github.com/curtisalexander/snowglobe@$snowglobeRef"
pi list
```

Restart Pi and confirm `submit_read_query` and `get_query_status` are available. The
package registers typed tools that invoke Snowglobe's fixed-loopback, result-free CLI;
it also bundles workflow guidance that Pi discovers as the `snowglobe` skill. The
runtime must remain running. See the [complete Pi integration guide](pi-integration.md)
for project-local installation, updates, removal, troubleshooting, and security detail.
Record `SNOWGLOBE_REF` as the Pi package revision in the private value-free evidence.

### Another shell-only agent, or Pi adapter debugging

Use the result-free CLI directly when an agent cannot load a native extension or when
debugging the Pi adapter. Keep `snowglobe-local` running, then pipe SQL through stdin:

```bash
printf '%s\n' 'SELECT * FROM YOUR_TEST_DATABASE.YOUR_TEST_SCHEMA.YOUR_APPROVED_VIEW' \
  | uv run snowglobe submit \
      --purpose "Constrained Snowglobe MVP canary check" \
      --ttl 300
```

On Windows PowerShell:

```powershell
'SELECT * FROM YOUR_TEST_DATABASE.YOUR_TEST_SCHEMA.YOUR_APPROVED_VIEW' | uv run snowglobe submit --purpose "Constrained Snowglobe MVP canary check" --ttl 300
```

Retain only the returned opaque ID and run
`uv run snowglobe status '<opaque-request-id>'` to poll it. The CLI deliberately has no
result, viewer, configuration, or cancellation commands. SQL is stdin-only so it is not
a `snowglobe` process argument. Do not have an agent call the `/v1` viewer routes,
inspect the browser, or use shell HTTP clients to read the result stream.

## 7. Verify the control surface

Native MCP clients must see exactly:

- `submit_read_query(sql, purpose, requested_ttl)`
- `get_query_status(request_id)`

It must not advertise Snowglobe resources, prompts, result readers, cancellation
tools, or connection-setting inputs. If the runtime was started without `--config`, a
submission correctly returns `SERVICE_UNAVAILABLE`.

The Pi extension must register exactly the same two tools, with closed input schemas,
and return only compact JSON text matching the receipt contracts. The CLI must expose
only `submit` and `status`. Successful invocation writes exactly one `QueryReceipt` or
`QueryStatusReceipt` JSON object to stdout. Neither adapter may emit result data,
schema, counts, Snowflake errors, identifiers, or result URLs. Malformed results and
invocations become closed receipts without reflecting their input.

## 8. Run the first agent experiment

Replace the relation below with one exact fully qualified entry from the private
profile's `allowed_views`. Do not include canary values in the prompt or SQL; they must
originate in the administrator-approved view.

> Use Snowglobe to submit this governed read query:
> `SELECT * FROM YOUR_TEST_DATABASE.YOUR_TEST_SCHEMA.YOUR_APPROVED_VIEW`.
> Use purpose `Constrained Snowglobe MVP canary check` and a TTL of 300 seconds.
> Return the opaque submission receipt, poll the request with Snowglobe until it is
> terminal, and report only the lifecycle receipt. Do not access the viewer backend,
> browser, result stream, screenshots, or local Snowflake configuration.

Expected agent-visible behavior:

1. submission returns only `status`, `request_id`, and `reason_code`;
2. status polling returns only `request_id` and `status`; and
3. a successful request eventually reaches `complete` without rows, schema, counts,
   timing, errors, Snowflake identifiers, or a result URL entering the conversation.

Open the Vite URL yourself, select the same request, and choose **Open result**. The
non-sensitive canary values and columns should appear there and nowhere in the agent
conversation. Reload or close the page after inspection to destroy browser worker
state.

Prompt instructions are usability guidance, not a security boundary. An agent with
arbitrary same-host browser, shell, or HTTP access may still reach loopback viewer
routes; Snowglobe guarantees only that its MCP tools do not create a result-bearing
channel.

## 9. Continue the MVP campaign

Run every case in the
[connected matrix](constrained-mvp-runbook.md#10-required-connected-checks-and-evidence),
including policy rejection, overflow, timeout, cancellation, expiry, and restart.
Copy the [value-free evidence template](mvp-evidence-template.md) outside the
repository and retain only the fields it permits.
