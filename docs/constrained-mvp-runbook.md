# Constrained Snowflake MVP test runbook

This runbook is the only supported procedure for Snowglobe's first connected test. It
is for a dedicated, non-production Snowflake environment containing only non-sensitive
canary data. It does not authorize production credentials, production data, routine
analyst use, remote exposure, or sensitive results.

`SECURITY.md` remains authoritative. Commands marked **connected** are permitted only
while every condition in its constrained connected-MVP exception remains true. Never
put a real `connections.toml`, a private key, query-result bytes, or Snowflake
administrative output in the repository, an agent transcript, a test artifact, or
ordinary logs.

## 1. Roles and stopping conditions

Two people or independently performed roles are required:

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
   - an allowed view with a variable-width cell larger than 16 KiB for cell-overflow
     rejection; and
   - an allowed bounded-result view whose execution remains pending long enough to
     test cancellation and the 60-second statement timeout without exceeding the
     resource monitor.
5. A separate, unapproved test view that the role either cannot select or that is
   intentionally omitted from Snowglobe's allowlist, for policy-rejection checks.

The allowed views must return no more than 32 columns except when deliberately testing
column overflow. No approved view may reference production or sensitive data.

Before the key is used, the administrator must independently confirm, using Snowflake
administrative interfaces rather than Snowglobe:

- grants to the test user and role contain no broader assigned or inherited role,
  ownership, create, insert, update, delete, truncate, merge, stage, procedure, or
  unintended object access, and `PUBLIC` provides no relevant access;
- the configured warehouse, database, role, and fully qualified views are exactly the
  intended test objects;
- the resource monitor is assigned and active; and
- query history and warehouse metering are visible to the administrator.

Record only pass/fail for these checks in the retained evidence. Do not copy grant
rows, account identifiers, object names, or administrative output into agent-visible
artifacts.

## 3. Local setup

Use Linux or macOS for the credential-bearing MVP runtime. Native Windows does not
provide the reviewed POSIX owner and no-follow file checks and is not currently a
supported connected host.

Install the exact locked project dependencies and optional connector:

```bash
./scripts/setup.sh
```

Copy `connections.example.toml` to an untracked path outside the repository when
possible. Populate exactly one test profile. `allowed_views` must contain only the
fully qualified administrator-approved views; use `database`, never `db`. Do not add
unknown fields.

The profile and key must be regular files owned by the operator, not symlinks, with no
group or other permissions. The owner must have read permission:

```bash
chmod 600 /absolute/private/path/connections.toml
chmod 600 /absolute/private/path/snowglobe-test-key.p8
```

Validate configuration, key parsing, and the SQL view allowlist without connecting:

```bash
uv run snowglobe-preflight \
  --config /absolute/private/path/connections.toml \
  --profile default
```

The only expected output is `Snowglobe preflight passed.` On failure, the only public
message is `Snowglobe preflight failed.` Resolve the local file or profile problem
without printing the profile, key, exception, or path contents.

## 4. Connected preflight

**Connected — permitted only by the constrained exception in `SECURITY.md`.**

Open and close one Snowflake cursor without executing SQL:

```bash
uv run snowglobe-preflight \
  --config /absolute/private/path/connections.toml \
  --profile default \
  --connect
```

Require the same fixed pass message. The administrator must then verify that the login
used the dedicated user, role, and warehouse and did not execute a statement. Stop if
the selected context differs from the reviewed configuration.

## 5. Launch

**Connected.** Start the single broker-owning runtime in one terminal:

```bash
uv run snowglobe-local \
  --config /absolute/private/path/connections.toml \
  --profile default
```

In a second terminal, start the loopback-only viewer development server:

```bash
npm run dev
```

Confirm the runtime health route succeeds and that both listeners use loopback:

```bash
curl --fail --silent http://127.0.0.1:8000/healthz
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`. Vite prints its loopback viewer URL,
normally `http://127.0.0.1:5173/`; use the printed URL if that port changes. Do not
start separate MCP and viewer-backend processes, bind either service to `0.0.0.0`, or
place a proxy or tunnel in front of them.

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
  "purpose": "Constrained Snowglobe MVP canary check",
  "requested_ttl": 300
}
```

For Pi, install the package as documented in the
[Pi integration guide](pi-integration.md), then call its native `submit_read_query`
tool with the same fields. The extension passes SQL to the result-free CLI over stdin.
Use the raw CLI only for adapter diagnosis.

Replace the example relation with one exact `allowed_views` entry. Keep identifiers
fully qualified. Do not put a result canary literal in SQL or `purpose`; the canary
must originate in the approved view. Functions are not allowed in submitted MVP SQL.

The accepted MCP, Pi tool, or CLI response must contain only `status`, `request_id`,
and `reason_code`. Poll `get_query_status` with only that `request_id`; for raw CLI
diagnosis, run `uv run snowglobe status '<opaque-request-id>'`. Each response must
contain only `request_id` and `status`. Continue until a terminal state. Do not infer
rows, counts, timing, or errors from the lifecycle state.

For a `complete` request, open the viewer, select the recent request or paste the same
ID, and choose **Open result**. Confirm the expected non-sensitive values and column
canaries appear only in the rendered viewer. Do not use browser developer tools,
screenshots, copy, export, or shell HTTP clients to inspect the result stream itself.
Reload or close the page after inspection to destroy the worker and in-memory DuckDB
state.

## 7. Cancellation

There is deliberately no MCP cancellation tool. Submit the administrator-approved
long-running bounded-result view, copy the accepted opaque ID, and cancel it through
the local viewer backend before it completes:

```bash
REQUEST_ID='<opaque MCP request ID>'
curl --fail --silent --request POST \
  "http://127.0.0.1:8000/v1/requests/${REQUEST_ID}/cancel"
```

The response may contain only `request_id`, `status: "cancelled"`, and `expires_at`.
Poll through MCP and require `cancelled`; the viewer must not offer a result. Repeat
the cancel request once and require it to remain `cancelled`. The administrator must
confirm cancellation or bounded termination in Snowflake query history and no
unexpected warehouse use.

## 8. Expiry

Submit an allowed bounded query with `requested_ttl: 10`. After acceptance, wait at
least 11 seconds, then poll it through MCP and look it up in the viewer. Require
`expired` and no available stream, whether execution had previously been pending or
complete. If it was still executing at expiry, the administrator must confirm bounded
termination in query history. The runtime caps every requested TTL at five minutes.

## 9. Graceful shutdown and restart

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

## 10. Required connected checks and evidence

Run the cases below while the administrator independently watches query history,
grants, resource-monitor state, and warehouse usage:

| Case | Required observation |
|---|---|
| Allowed bounded canary | `accepted` → `pending` or `complete` → `complete`; complete result visible only in viewer |
| Empty result | `complete`; declared columns render with no rows |
| Multiple batches | `complete`; all admitted rows render once and in order |
| More than 50 rows, 32 columns, 16-KiB cell, or 256-KiB Arrow/decoded | `failed`; no stream is published |
| Mutation, multiple statements, unapproved object or function, stage syntax | `POLICY_REJECTED`; no Snowflake query-history entry |
| Tool-supplied profile, role, warehouse, database, authenticator, or key path | closed-schema rejection; no Snowflake query-history entry |
| Statement timeout, driver failure, or cleanup failure | only `failed`; no driver detail through MCP or ordinary output |
| Cancellation | only `cancelled`; no result source; bounded Snowflake termination |
| Expiry | only `expired`; no result source; bounded Snowflake termination if still running |
| Runtime restart | pending work bounded; old ID becomes `not_found`; nothing restored |

For every native MCP case, check that text and structured results contain the same
closed fields. For Pi, check that exactly two tools are registered and tool content is
one closed receipt. For CLI and Pi subprocess cases, check that stdout is bounded to
one closed JSON receipt and stderr contains no submitted or result data. Result values
and column names must be absent from all captured MCP traffic, Pi tool results, and CLI
output; submitted SQL must not be reflected in responses. Result values, column names,
SQL, Snowflake identifiers, counts, sizes, timing, and errors must be absent from
process output, ordinary logs, and URLs. In the browser's Application inspection,
confirm Local Storage, Session Storage, IndexedDB, Cache Storage, and OPFS contain no
result data and that no service worker is registered; do not inspect the result stream
in the Network panel.

Copy the [value-free evidence template](mvp-evidence-template.md) outside the
repository and retain only the permitted fields: date, software revision, case name,
pass/fail, lifecycle/reason code, and administrator confirmation of bounded execution
and expected grants/usage. Opaque request IDs may be recorded but are not required. Do
not retain query results, screenshots, SQL text, profile values, object/account names,
query IDs, driver errors, query-history rows, timings, sizes, or usage values.

Finally run `./scripts/check.sh` and retain only the individual command names, exit
status, and summary counts. The script runs:

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

MVP evidence is complete only when every row in the connected matrix and every local
check passes without result-derived information escaping the viewer path.
