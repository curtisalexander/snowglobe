# Connected Snowflake MVP validation runbook

Use this runbook for Snowglobe's first connected validation in a non-production
Snowflake environment containing non-sensitive canary data. It is not yet a production
readiness claim.

`SECURITY.md` remains authoritative. Never commit a real `connections.toml`, a private
key, or result data. Never paste credentials, result data, or local operator diagnostics
into an agent transcript.

## 1. Roles and stopping conditions

The same analyst may perform both roles; a second person is not required:

- The **Snowflake administrator** provisions and inspects the test account, role,
  user, warehouse, resource monitor, views, query history, usage, and grants outside
  Snowglobe.
- The **operator** controls the local Snowglobe process and browser.

Stop the test and shut down Snowglobe if any of these conditions is false:

- the account is dedicated non-production, or the test role is isolated from
  production;
- every test object contains only non-sensitive synthetic canaries;
- the test user cannot assume a broader role;
- the role has access only to the approved test views;
- a small dedicated warehouse has an active administrator-owned resource monitor;
- the administrator can inspect query history, warehouse usage, and grants during the
  test; or
- either process would bind anywhere other than `127.0.0.1`.

## 2. Administrator-owned environment setup

The administrator must create or select all of the following before giving the
operator a key:

1. A dedicated test user using key-pair authentication. The dedicated test role must
   be its default and only assigned role. Snowflake's unavoidable `PUBLIC` role must
   have no access to the test objects or any broader data available to this test user.
2. A dedicated read-only role with only:
   - usage on the test warehouse, database, and schema; and
   - select on each explicitly approved test view.
3. A small dedicated warehouse with auto-suspend and auto-resume configured and an
   administrator-owned resource monitor that limits credit consumption for the test
   window.
4. A test database and schema containing these administrator-owned views:
   - a bounded allowed view with non-sensitive canaries in values and column names;
   - an allowed empty view that preserves a declared schema;
   - an allowed view expected to return several Arrow batches, if the connector and
     account produce them at the 50-row limit;
   - an allowed view with at least 51 rows for row-overflow rejection;
   - an allowed view with at least 33 columns for column-overflow rejection;
   - an allowed view with a variable-width cell larger than 16 KiB for cell-overflow
     rejection;
   - an allowed view whose cells are each no larger than 16 KiB but whose cumulative
     decoded or serialized Arrow representation exceeds 256 KiB; and
   - an allowed bounded-result view whose execution remains pending long enough to
     test cancellation and the 60-second statement timeout without exceeding the
     resource monitor.
5. A separate, unapproved test view that the role either cannot select or that is
   intentionally omitted from Snowglobe's allowlist, for policy-rejection checks.

The allowed views must return no more than 32 columns except when deliberately testing
column overflow. No approved view may reference production or sensitive data.

Before the key is used, confirm through Snowflake rather than Snowglobe:

- grants to the test user and role contain no broader assigned or inherited role,
  ownership, create, insert, update, delete, truncate, merge, stage, procedure, or
  unintended object access, and `PUBLIC` provides no relevant access;
- the configured warehouse, database, role, and fully qualified views are exactly the
  intended test objects;
- the resource monitor is assigned and active; and
- query history and warehouse metering are visible to the administrator.

## 3. Local setup

Use Linux, macOS, or native Windows 10/11 for the credential-bearing MVP runtime.
On Windows, keep configuration and key files in an analyst-controlled location.

Install the exact locked project dependencies and optional connector:

```bash
./scripts/setup-dev.sh
```

On Windows PowerShell, run `./scripts/setup-dev.ps1`.

Use an existing native Snowflake `connections.toml`, or copy
`connections.example.toml` to an untracked path outside the repository. Copy
`snowglobe.example.toml` separately. Populate matching test profiles. The Snowglobe
profile's `allowed_views` must contain only the fully qualified
administrator-approved views; use `database`, never `db`.

Keep the profile and key untracked and manage them like your other local credentials.
Snowglobe does not inspect ownership or permissions.

Validate configuration, key parsing, and the SQL view allowlist without connecting:

```bash
uv run snowglobe-preflight \
  --connections /absolute/private/path/connections.toml \
  --snowglobe-config /absolute/private/path/snowglobe.toml \
  --profile default
```

Successful output is `Snowglobe preflight passed.` On failure, use the reported local
path or configuration detail to correct the profile or key.

## 4. Connected preflight

Open and close one Snowflake cursor without executing SQL:

```bash
uv run snowglobe-preflight \
  --connections /absolute/private/path/connections.toml \
  --snowglobe-config /absolute/private/path/snowglobe.toml \
  --profile default \
  --connect
```

Require the same fixed pass message. Then verify that the login used the dedicated user,
role, and warehouse and did not execute a statement. Stop if the selected context
differs from the reviewed configuration.

## 5. Launch

Start the single broker-owning runtime in one terminal:

```bash
uv run snowglobe-local \
  --connections /absolute/private/path/connections.toml \
  --snowglobe-config /absolute/private/path/snowglobe.toml \
  --profile default
```

In a second terminal, start the loopback-only viewer development server:

```bash
npm run dev
```

Confirm the runtime health route succeeds:

```bash
curl --fail --silent http://127.0.0.1:8000/healthz
```

On Linux, inspect the matching listener rows:

```bash
ss -ltnp | grep -E ':(8000|5173)\b'
```

On macOS, use `lsof` instead:

```bash
lsof -nP -iTCP:8000 -iTCP:5173 -sTCP:LISTEN
```

On Windows PowerShell, inspect both listeners:

```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalPort -In 8000,5173 | Select-Object LocalAddress,LocalPort,OwningProcess
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`. Vite prints its loopback viewer URL,
normally `http://127.0.0.1:5173/`; use the printed URL if that port changes. Do not
start separate MCP and viewer-backend processes, bind either service to `0.0.0.0`, or
place a proxy or tunnel in front of them. The listener inspection must show only
`127.0.0.1` for both processes; a successful loopback health request alone does not
prove that they are not also exposed on another interface.

Configure a native test MCP client with only the MCP endpoint, or install Snowglobe's
native Pi package. Connection profile, role, warehouse, database, authenticator, and
key path are launcher-owned and must never be tool, extension, or CLI arguments. The
[getting-started guide](getting-started.md) provides setup for Amp, Codex, Claude Code,
Continue.dev, and Pi, plus the expected control surface and a first prompt.

## 6. Submit, poll, and inspect

Submit through the `submit_read_query` MCP tool with arguments shaped exactly as:

```json
{
  "sql": "SELECT * FROM MVP_DATABASE.MVP_SCHEMA.ALLOWED_CANARY_VIEW",
  "requested_ttl": 300
}
```

For Pi, install the package as documented in the
[Pi integration guide](pi-integration.md), then call its native `submit_read_query`
tool with the same fields. The extension passes SQL to the result-free CLI over stdin.
Use the raw CLI only for adapter diagnosis.

Replace the example relation with one exact Snowglobe `allowed_views` entry. Keep
identifiers fully qualified. Do not put a result canary literal in SQL; the canary must
originate in the approved view.

The accepted MCP, Pi tool, or CLI response must contain only `status`, `request_id`,
and `reason_code`. Poll `get_query_status` with only that `request_id`; for raw CLI
diagnosis, run `uv run snowglobe status '<opaque-request-id>'`. Each response must
contain only `request_id` and `status`. Continue until a terminal state. Do not infer
rows, counts, timing, or errors from the lifecycle state.

For a `complete` request, open the viewer, select the recent request or paste the same
ID, and choose **Open result**. Confirm the expected non-sensitive values and column
canaries appear in the rendered viewer. Browser developer tools and screenshots are
fine for this non-sensitive validation, but they are not evidence about what MCP
returned. Reload or close the page after inspection to destroy the worker and in-memory
DuckDB state.

## 7. Expiry

Submit an allowed bounded query with `requested_ttl: 10`. After acceptance, wait at
least 11 seconds, then poll it through MCP and look it up in the viewer. Require
`expired` and no available stream, whether execution had previously been pending or
complete. If it was still executing at expiry, the administrator must confirm bounded
termination in query history. The runtime caps every requested TTL at five minutes.

## 8. Graceful shutdown and restart

Close the viewer tab first so its application worker and DuckDB instance are
destroyed. Stop Vite with `Ctrl-C`. Stop `snowglobe-local` with `Ctrl-C` and wait for
the process to exit; graceful shutdown cancels pending broker requests and waits for
request-scoped connector cleanup. Do not use `kill -9` for the normal test.

To verify restart behavior, submit the long-running bounded-result query, retain only
its opaque request ID, and gracefully stop the runtime while it is pending. The
administrator must confirm the query is cancelled or stopped by the configured
60-second statement timeout and detached-query controls. Start the runtime again with
the exact command in section 5. The old ID must return `not_found` through MCP and 404
through the viewer backend; no request or result may be restored. This loss is the
documented MVP behavior.

After every connected test session, gracefully stop both processes and confirm with
the administrator that no test query is running and the dedicated warehouse has
auto-suspended. Remove local credentials when the test campaign is complete according
to the administrator's key-revocation procedure.

## 9. Required connected checks and evidence

Run the cases below while watching query history, grants, resource-monitor state, and
warehouse usage through Snowflake:

| Case | Required observation |
|---|---|
| Allowed bounded canary | `accepted` → `pending` or `complete` → `complete`; complete result visible only in viewer |
| Empty result | `complete`; declared columns render with no rows |
| Multiple batches, when the connector/account produces them at the 50-row cap | `complete`; all admitted rows render once and in order; otherwise record N/A and retain the deterministic local multi-batch test result |
| More than 50 rows, 32 columns, 16-KiB cell, or 256-KiB Arrow/decoded | `failed`; no stream is published |
| Mutation, multiple statements, unapproved object, unknown table function, `RESULT_SCAN`, or stage syntax | `POLICY_REJECTED`; no Snowflake query-history entry |
| Local `GENERATOR` or `FLATTEN` | Accepted when the rest of the query satisfies policy |
| Tool-supplied profile, role, warehouse, database, authenticator, or key path | closed-schema rejection; no Snowflake query-history entry |
| Statement timeout or administrator-aborted pending query | only `failed`; no driver detail through MCP, CLI, or Pi |
| Cancellation | only `cancelled`; no result source; bounded Snowflake termination |
| Expiry | only `expired`; no result source; bounded Snowflake termination if still running |
| Runtime restart | pending work bounded; old ID becomes `not_found`; nothing restored |

For every native MCP case, check that text and structured results contain the same
closed fields. For Pi, check that exactly two tools are registered and tool content is
one closed receipt. For CLI and Pi subprocess cases, check that stdout is bounded to
one closed JSON receipt and stderr contains no submitted or result data. Result values
and column names must be absent from all captured MCP traffic, Pi tool results, and CLI
output; submitted SQL must not be reflected in those responses. Confirm that the
Snowflake connector logger remains disabled because it is not safe for result-bearing
queries. In the browser's Application inspection, confirm Local Storage, Session
Storage, IndexedDB, Cache Storage, and OPFS contain no result data and that no service
worker is registered. Inspecting the Network stream is allowed but is not MCP-boundary
evidence.

For the administrator-aborted-query case, submit the approved long-running bounded
view and have the administrator terminate that query from Snowflake while it is
pending. This is the connected driver-failure injection; do not alter grants,
credentials, allowlists, network settings, or test objects. Cleanup-failure behavior
is not safely injectable in the connected environment and is covered by the local
fake-connector suite instead.

Use the [boundary evidence template](mvp-evidence-template.md) to record the software
revision, case outcomes, and the exact MCP/CLI/Pi output assertions. Keep credentials
out of evidence. Because this campaign uses non-sensitive canaries, screenshots and
Snowflake diagnostics may be retained when useful; do not treat them as proof of what
entered model context.

Finally run `./scripts/check-dev.sh` (or `./scripts/check-dev.ps1` on Windows) and retain only
the individual command names, exit status, and summary counts. The script runs:

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
npm run lint
npm run typecheck
npm test
npm run build
```

MVP evidence is complete only when every applicable row in the connected matrix and
every local check passes without result-derived information escaping the viewer path.
The multiple-batch row is the only case that may be N/A, and only for the connector
behavior described above.
