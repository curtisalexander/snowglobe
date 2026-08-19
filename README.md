# Snowglobe

<p align="center">
  <img src="assets/snowglobe-logo.webp" alt="A duck, snowflake, and streams of data contained inside a snow globe" width="420">
</p>

**A local Snowflake query MCP and result viewer for one analyst.**

Snowglobe lets a coding agent submit governed read-only SQL without putting the query
result into the MCP response. Submission will run asynchronously and return an opaque
request ID. The agent may poll that ID for a small lifecycle state, while the analyst
uses the same ID in a local viewer to inspect the result.

```text
                         MCP — control only
┌──────────────┐     ┌────────────────────────┐     ┌───────────┐
│ Analyst's    │────▶│ local Snowglobe runtime│────▶│ Snowflake │
│ coding agent │◀────│ submit + status        │     │           │
└──────────────┘     └───────────┬────────────┘     └─────┬─────┘
       opaque ID + lifecycle     │                        │
                                 │ shared local broker    │
                                 ▼                        │
                      ┌──────────────────────┐             │
                      │ local viewer backend│◀────────────┘
                      └──────────┬───────────┘
                                 │ admitted Arrow stream
                                 ▼
                      ┌──────────────────────┐
                      │ browser worker      │
                      │ + DuckDB-Wasm       │
                      └──────────────────────┘
```

There are no viewer accounts, enterprise OIDC, tenants, owner claims, or sharing. MCP
and viewer routes run in one process and bind to loopback for individual use.

## Status

Snowglobe is still a test-environment MVP and is **not ready for production
credentials, sensitive data, or routine analyst use**. One dedicated non-production
test credential is permitted only under the
[constrained MVP runbook](docs/constrained-mvp-runbook.md). Implemented pieces include:

- explicit low-level MCP contracts for `submit_read_query` and
  `get_query_status`;
- a single-analyst broker with pending, complete, failed, cancelled, and expired
  lifecycle states;
- a configured background Snowflake executor that registers a request-scoped cursor
  before acceptance, fetches incrementally, and publishes only admitted results;
- local viewer routes to list, find, cancel, and stream a request;
- incremental Arrow admission and failure-atomic framing; and
- in-memory DuckDB-Wasm ingestion with a bounded main-thread viewport.

The submit tool returns `SERVICE_UNAVAILABLE` unless the supported launcher is
explicitly given a local configuration file. The real executor and minimum browser
boundary assurance and the [Gate 5 constrained-test runbook](docs/constrained-mvp-runbook.md)
now exist. `SECURITY.md` authorizes only that constrained connected test.

- [Implementation plan](PLAN.md)
- [Constrained MVP test runbook](docs/constrained-mvp-runbook.md)
- [Single-analyst architecture decision](docs/decisions/0008-single-analyst-loopback-runtime.md)
- [Threat model](docs/threat-model.md)
- [Security policy](SECURITY.md)
- [Documentation index](docs/README.md)

## Boundary

MCP may return only:

- an accepted/rejected submission receipt with an opaque request ID and fixed reason;
  or
- an opaque request ID plus `pending`, `complete`, `failed`, `cancelled`, `expired`,
  `not_found`, or `service_unavailable`.

MCP must not return rows, schema, column names, counts, sizes, timing, Snowflake query
IDs, database errors, result URLs, or result-derived artifacts. Result bytes travel
only through the local viewer backend into the browser worker.

Loopback is not authentication or process isolation. A coding agent with arbitrary
same-host HTTP, browser, shell, or process access may be able to call the local viewer
backend or capture rendered data. Snowglobe prevents an automatic result-bearing MCP
channel; it does not claim to defend the analyst's data from other processes running as
that analyst.

## Local development

Requirements are Python 3.12 with `uv`, plus Node.js 22.12 or newer and npm.

```bash
uv sync
npm install

# One loopback process owns MCP, viewer routes, and the in-memory broker.
uv run snowglobe-local

# In another terminal; Vite proxies viewer API calls to the local runtime.
npm run dev
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`. Do not launch the MCP and viewer
backend as separate processes while the broker is in memory, and do not bind either
service to `0.0.0.0`.

Run all checks with:

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

The Snowflake executor reads a local `connections.toml` profile. Start from
[`connections.example.toml`](connections.example.toml); never commit the real file or
private key. Snowglobe accepts both files only when they are regular files owned by the
current user, are not symlinks, and grant no permissions to the group or other users.
The owner must have read permission and may have write permission (`0400` or `0600`):

```bash
chmod 600 connections.toml /path/to/snowflake-key.p8
```

Validate the local profile and key without connecting to Snowflake:

```bash
uv run snowglobe-preflight --config connections.toml --profile default
```

The explicit `--connect` mode is permitted only by the constrained MVP test procedure.
It opens and closes one Snowflake cursor, executes no SQL, and prints only a fixed
pass/fail message.

The local service's `--config connections.toml --profile default` options explicitly
enable configured execution. They are likewise reserved for the Gate 5 procedure;
starting without `--config` remains fail-closed. The connected procedure must install
the optional connector first with `uv sync --extra snowflake`.

The constrained MVP accepts one pending request for at most five minutes. Connection
timeouts are 30 seconds for login, 60 seconds for network retries, and 15 seconds per
socket operation. Snowflake statements have a 60-second server deadline and a
15-second queue deadline. Results are limited to 50 rows, 32 columns, 16 KiB per cell,
and 256 KiB serialized and decoded Arrow so the complete admitted result fits the
current viewer.

Each profile also has an exact `allowed_views` list. MVP queries must reference one of
those views as a fully qualified `DATABASE.SCHEMA.VIEW`. The initial function allowlist
is intentionally empty: functions, UDFs, table functions, stages, variables, and
partially qualified relations are rejected until separately reviewed.

## License

[MIT](LICENSE) © 2026 Curtis Alexander
