# Snowglobe developer guide

This guide is the fastest path to understanding, reviewing, and changing the
implemented Snowglobe MVP. It explains the current code rather than the older retained
architecture proposal. Use it alongside:

- [PLAN.md](../PLAN.md) for scope, status, and deferred work;
- [SECURITY.md](../SECURITY.md) for the authoritative security policy;
- [the ADR index](decisions/README.md) for why consequential choices were made; and
- [the getting-started guide](getting-started.md) when you want to run the product.

## 1. The system in one page

Snowglobe lets an agent submit one tightly governed Snowflake read query while keeping
result-derived data out of model-facing control channels. A transport-neutral control
plane returns exact governed SQL with an opaque request ID, followed by coarse lifecycle
states, through either MCP or a result-free CLI client. Pi uses native typed tools that
wrap that CLI and independently validate its receipts. The local viewer is the data
plane: it streams a complete admitted Arrow result into an in-memory DuckDB-Wasm
instance in a dedicated browser worker.

```text
                       MCP or CLI control
┌──────────────┐     ┌─────────────────────────┐     ┌───────────┐
│ Coding agent │────▶│ Local Snowglobe runtime │────▶│ Snowflake │
│              │◀────│ submit + status only    │     │           │
└──────────────┘     └────────────┬────────────┘     └─────┬─────┘
                                  │                        │
                                  │ process-local broker   │ Arrow batches
                                  ▼                        │
                       ┌──────────────────────┐            │
                       │ Viewer HTTP routes   │◀───────────┘
                       └──────────┬───────────┘
                                  │ framed Arrow stream
                                  ▼
                       ┌──────────────────────┐
                       │ Browser app worker   │
                       │ + in-memory DuckDB   │
                       └──────────┬───────────┘
                                  │ bounded viewport
                                  ▼
                       ┌──────────────────────┐
                       │ Svelte main thread   │
                       └──────────────────────┘
```

There is one analyst, one loopback runtime, one in-process broker, at most one pending
query, and no durable request state. Restarting the runtime intentionally loses all
requests and results.

### The three publication barriers

Most of the architecture follows from three ordering guarantees:

1. **MCP acceptance waits for registration.** `accepted` is returned only after policy
   authorization, pending registration, and successful background-task scheduling.
2. **Broker completion waits for admission and cleanup.** `complete` is published only
   after all Arrow batches pass every limit and the request-scoped cursor and connection
   have closed.
3. **Browser publication waits for a terminal frame.** DuckDB ingests into a private
   pending table. That table is renamed to the published table only after the parser
   sees a valid completion frame at clean end-of-stream.

If a future change weakens any one of these barriers, it changes a security boundary.

## 2. Non-negotiable boundaries

Read [AGENTS.md](../AGENTS.md) and [SECURITY.md](../SECURITY.md) before changing a
boundary. The implementation assumes all of the following:

- MCP advertises exactly `submit_read_query` and `get_query_status`.
- MCP never returns rows, schema, column names, counts, sizes, timings, Snowflake IDs,
  driver errors, result locations, or result artifacts.
- Accepted submission receipts return exact governed SQL; rejected receipts return
  `governed_sql: null`.
- MCP text content and structured content encode the same closed receipt.
- CLI stdout contains exactly the same closed receipt models and never result data.
- Pi registers exactly those two tools, independently validates CLI receipts, and
  returns only compact receipt JSON with empty tool details.
- Profile, role, warehouse, database, authenticator, key path, and allowlisted views
  come only from local launcher configuration, never tool input.
- SQL authorization parses one read query and recursively verifies every external
  relation against configured views before applying the row cap.
- Arrow retrieval and admission remain incremental. Do not add `fetchall()`,
  `fetch_arrow_all()`, `to_pylist()`, complete result concatenation, or row dictionaries.
- Result bytes travel only through loopback viewer routes into the browser worker.
- The browser creates no IndexedDB, OPFS, service-worker cache, automatic restoration,
  export, telemetry, or external DuckDB reader surface.
- Loopback is exposure reduction, not viewer authentication or same-host isolation.

The accepted decisions behind these rules are primarily
[ADR 0008](decisions/0008-single-analyst-loopback-runtime.md),
[ADR 0009](decisions/0009-constrained-snowflake-mvp-budgets.md),
[ADR 0010](decisions/0010-minimum-snowflake-select-policy.md), and
[ADR 0011](decisions/0011-bounded-snowflake-execution.md), as refined by
[ADR 0019](decisions/0019-relation-centric-sql-authorization.md).

## 3. Repository map

```text
snowglobe/
├── src/snowglobe/          Python runtime, policy, execution, broker, HTTP
├── apps/viewer/src/        Svelte UI, stream parser, worker, DuckDB-Wasm
├── integrations/pi/        Native Pi tools and process boundary
├── tests/                  Backend and cross-boundary pytest suite
├── docs/decisions/         Accepted architecture decisions
├── docs/                   Runbooks, threat model, and implementation guides
├── scripts/setup-dev.sh    Locked developer installation
├── scripts/setup-dev.ps1   Locked Windows developer installation
├── scripts/check-dev.sh    Complete connection-free verification
├── scripts/check-dev.ps1   Complete Windows connection-free verification
├── pyproject.toml          Python package, entry points, and tool configuration
└── package.json            Viewer commands and Pi package manifest
```

### Developer setup and daily loop

On Linux, macOS, or Windows, install Python 3.12+, `uv`, Node.js 22.19+, and npm. Then,
from a fresh clone on Linux or macOS:

```bash
./scripts/setup-dev.sh
./scripts/check-dev.sh
```

On Windows PowerShell, run `./scripts/setup-dev.ps1` and `./scripts/check-dev.ps1`.

The setup script installs the exact Python lock, including the optional Snowflake
connector, and the exact npm lock. The check script is connection-free and is the
normal pre-commit verification path.

For a fail-closed local development session that cannot execute Snowflake queries:

```bash
# Terminal 1: MCP, viewer routes, and broker
uv run snowglobe-local

# Terminal 2: Svelte/Vite viewer with a backend proxy
npm run dev
```

The result routes have no standalone application export. Always use `snowglobe-local`:
the MVP broker is process-local and must be shared by MCP and the viewer routes. For a
configured connected session, use the complete profile, preflight, launch, client,
prompt, and shutdown procedure in the
[getting-started guide](getting-started.md). Do not commit `connections.toml` or a key.

### Backend ownership

| File | Owns |
|---|---|
| [`local_server.py`](../src/snowglobe/local_server.py) | Supported loopback launcher, route composition, executor shutdown |
| [`runtime.py`](../src/snowglobe/runtime.py) | Explicit process-local broker, executor, and control-plane composition |
| [`control.py`](../src/snowglobe/control.py) | Transport-neutral submission, status lookup, and fixed receipt mapping |
| [`mcp_gateway.py`](../src/snowglobe/mcp_gateway.py) | Exact MCP schemas, argument validation, framing, and receipt serialization |
| [`cli.py`](../src/snowglobe/cli.py) | Result-free shell adapter over the running loopback MCP service |
| [`contracts.py`](../src/snowglobe/contracts.py) | Closed Pydantic receipt and lifecycle types |
| [`configuration.py`](../src/snowglobe/configuration.py) | Exact TOML profile schema and connector argument allowlist |
| [`private_key.py`](../src/snowglobe/private_key.py) | PEM/DER RSA parsing and PKCS#8 conversion |
| [`sql_policy.py`](../src/snowglobe/sql_policy.py) | One read query, approved views, and server-owned row cap |
| [`executor.py`](../src/snowglobe/executor.py) | Generic async admission/startup/expiry/publication ordering |
| [`snowflake_executor.py`](../src/snowglobe/snowflake_executor.py) | Real connector work, one-execution lock, incremental Arrow retrieval |
| [`snowflake.py`](../src/snowglobe/snowflake.py) | Request-scoped connection and cursor context manager |
| [`broker.py`](../src/snowglobe/broker.py) | Request state, private cursor association, source publication, cancellation, expiry |
| [`arrow_stream.py`](../src/snowglobe/arrow_stream.py) | Arrow schema/cell/row/byte admission and incremental IPC serialization |
| [`result_api.py`](../src/snowglobe/result_api.py) | Viewer metadata and failure-atomic framed streaming routes |
| [`mvp_limits.py`](../src/snowglobe/mvp_limits.py) | Shared backend MVP budgets |
| [`preflight.py`](../src/snowglobe/preflight.py) | Local and connected profile checks with operator diagnostics |

### Pi package ownership

| File | Owns |
|---|---|
| [`package.json`](../package.json) | Pi package discovery manifest and integration checks |
| [`index.ts`](../integrations/pi/extensions/index.ts) | Exact native tool definitions and closed tool results |
| [`contracts.ts`](../integrations/pi/extensions/contracts.ts) | Independent exact JSON receipt validation and fixed failures |
| [`process.ts`](../integrations/pi/extensions/process.ts) | No-shell subprocess, stdin SQL, cancellation, timeout, and bounded output |

### Viewer ownership

| File | Owns |
|---|---|
| [`App.svelte`](../apps/viewer/src/App.svelte) | Request discovery, explicit open action, worker lifecycle, table rendering |
| [`main.ts`](../apps/viewer/src/main.ts) | Svelte application mount point |
| [`result-api.ts`](../apps/viewer/src/result-api.ts) | Strict viewer-route response parsing and stream opening |
| [`result-stream.ts`](../apps/viewer/src/result-stream.ts) | Binary framing parser and provisional publication protocol |
| [`arrow-ingest.ts`](../apps/viewer/src/arrow-ingest.ts) | Backpressured Arrow record-batch ingestion into DuckDB |
| [`worker.ts`](../apps/viewer/src/worker.ts) | Main-thread worker RPC, transferred chunks, abort, and destruction |
| [`duckdb.worker.ts`](../apps/viewer/src/duckdb.worker.ts) | DuckDB-Wasm instance, pending/published tables, bounded queries |
| [`viewport.ts`](../apps/viewer/src/viewport.ts) | Bounded conversion of one viewport to renderable strings |
| [`mvp-limits.ts`](../apps/viewer/src/mvp-limits.ts) | Browser result and viewport ceilings |
| [`vite.config.ts`](../apps/viewer/vite.config.ts) | Loopback Vite binding and `/v1` proxy to the runtime |

## 4. Startup and process composition

The executable entry points are declared in [`pyproject.toml`](../pyproject.toml):

```toml
[project.scripts]
snowglobe = "snowglobe.cli:main"
snowglobe-local = "snowglobe.local_server:main"
snowglobe-preflight = "snowglobe.preflight:main"
```

`snowglobe-local` follows this order:

```text
local_server.main
├── parse --connections, --snowglobe-config, and --profile
├── create_runtime
│   ├── create one InProcessBroker
│   ├── if both configuration paths are present, create_snowflake_executor
│   │   ├── load_snowflake_profile and load_snowglobe_profile
│   │   ├── construct SnowflakeSqlPolicy
│   │   ├── build_connector_arguments
│   │   └── construct BackgroundQueryExecutor
│   └── construct ControlPlane(broker, executor)
├── create_server(runtime.control)
├── compose MCP and viewer routes around the same runtime
└── uvicorn.run(host="127.0.0.1", port=8000)
```

[`runtime.create_runtime()`](../src/snowglobe/runtime.py) creates the single broker with
a five-minute maximum TTL and one-pending-request capacity, the optional configured
executor, and their shared `ControlPlane`. [`local_server.create_app()`](../src/snowglobe/local_server.py)
prepends the viewer routes to an MCP server constructed around that control plane, so
both route sets refer to the runtime's exact broker object. On application shutdown,
its lifespan closes the runtime, which cancels pending requests and waits for worker
tasks to finish connector cleanup.

Starting without both configuration paths constructs the control plane with no
executor; submission then returns `SERVICE_UNAVAILABLE`. Supplying only one path fails
startup. This is the fail-closed development mode, not a partially configured
executor.

## 5. Configuration and credential path

[`configuration.load_snowflake_profile()`](../src/snowglobe/configuration.py) reads a
top-level profile from a native Snowflake `connections.toml`. It requires the fixed
account, user, authenticator, private-key file, database, warehouse, and role fields;
other native profiles and fields may remain but are not forwarded.

[`configuration.load_snowglobe_profile()`](../src/snowglobe/configuration.py) reads the
matching profile from a separate, versioned `snowglobe.toml`. Its exact policy schema
contains `allowed_views`; unknown or missing fields fail.

Configuration uses normal reads from the analyst-supplied paths. Snowglobe relies on
the analyst and operating system for file access policy.

[`load_private_key()`](../src/snowglobe/private_key.py) parses an unencrypted PEM or DER
RSA key and converts it in memory to the unencrypted PKCS#8 DER bytes expected by the
Snowflake connector.

`build_connector_arguments()` is the connector boundary. It explicitly supplies the
profile values plus one prefetch thread, login/network/socket timeouts, statement and
queue timeouts, and `ABORT_DETACHED_QUERY`. It never forwards the TOML document or
accepts arbitrary connector options.

Preflight uses the same loading, key conversion, policy construction, and connector
argument path as runtime startup. Without `--connect`, it never calls Snowflake. With
`--connect`, it opens and closes one cursor without executing SQL. Success is a fixed
message; failures include local configuration or connection detail for the operator.

## 6. Control-plane adapters and contracts

[`control.py`](../src/snowglobe/control.py) owns transport-neutral submission, lifecycle
lookup, and conversion of policy or internal failures to closed Pydantic receipts. It
does not know about MCP framing, CLI parsing, or viewer routes.

[`mcp_gateway.py`](../src/snowglobe/mcp_gateway.py) uses the low-level
`mcp.server.Server` API. It explicitly defines tools, schemas, dispatch, text content,
structured content, and public failures. `create_server(control)` binds each MCP server
instance to explicit dependencies rather than mutable module globals.

Submission input is exactly:

```json
{
  "sql": "SELECT * FROM APPROVED_DB.APPROVED_SCHEMA.APPROVED_VIEW",
  "requested_ttl": 300
}
```

An accepted result is exactly:

```json
{
  "status": "accepted",
  "request_id": "opaque-random-request-id",
  "reason_code": "NONE",
  "governed_sql": "SELECT * FROM APPROVED_DB.APPROVED_SCHEMA.APPROVED_VIEW LIMIT 51"
}
```

Status input contains only `request_id`; status output contains only `request_id` and
one coarse state. Both schemas set `additionalProperties: false`.

Every public exception boundary maps details to a fixed receipt. Invalid status input
gets a fresh opaque ID plus `not_found`, rather than reflecting malformed input.
Unknown tool names receive the fixed text `Tool unavailable.`

[`cli.py`](../src/snowglobe/cli.py) lets Pi and other shell-only agents reach the same
running MCP server. `snowglobe submit` reads SQL from stdin; `snowglobe status` accepts
only an opaque request ID. The CLI validates MCP structured content back into the
closed receipt models before printing one compact JSON object. A transport failure or
malformed response becomes a fixed service-unavailable receipt. The CLI never creates
its own runtime and exposes no viewer or result command.

[`integrations/pi/extensions/index.ts`](../integrations/pi/extensions/index.ts) is the
preferred Pi adapter. It registers exactly the same two names and input shapes as
native typed Pi tools, invokes the package-local CLI with `uv run --project ...
--frozen`, and returns compact JSON text with empty details. The process wrapper uses
an argument array rather than a shell, pipes SQL through stdin, discards stderr, bounds
stdout, and honors cancellation and fixed timeouts. The extension then validates the
CLI result independently against exact TypeScript receipt contracts. Any process or
validation failure becomes a fixed closed receipt.

See [ADR 0014](decisions/0014-pi-extension-package.md) and the
[Pi integration guide](pi-integration.md).

## 7. SQL authorization and rewriting

[`SnowflakeSqlPolicy.authorize()`](../src/snowglobe/sql_policy.py) applies the small
application query policy. The normative contract and broader example corpus are in the
[governed SQL policy](sql-policy.md):

```text
submitted SQL
    │
    ▼
parse exactly one Snowflake statement
    │
    ▼
require one read-query root
    │
    ├── allow CTE references
    └── require external DATABASE.SCHEMA.VIEW allowlist matches
    │
    ▼
apply top-level LIMIT 51 unless a smaller literal limit exists
    │
    ▼
generate, parse, and authorize the exact SQL that will execute
```

The 51-row cap is `K + 1` for a 50-row result budget. It lets Arrow admission detect
an oversized result instead of silently presenting a truncated result as complete.
The accepted submission receipt returns this final governed SQL, correlated with its
opaque request ID. The configured executor also prints the same pair to the foreground
local runtime immediately before the connector call. It does not add SQL to broker
views or lifecycle receipts.

For example, this approved input:

```sql
SELECT account_id, balance
FROM TEST_DB.GOVERNED.APPROVED_BALANCES
ORDER BY account_id
```

is regenerated with a server-owned top-level `LIMIT 51`. A model-supplied larger
literal limit is replaced; a smaller one is preserved. Ordinary scalar expressions,
functions, and set operations are accepted. Structurally local `GENERATOR` and
`FLATTEN` row sources are accepted. Other table functions, `RESULT_SCAN`, stage
directory sources, and unknown relation shapes are rejected because they can read data
without an approved table node. DDL, DML, multiple statements, and unapproved or
partially qualified external relations are also rejected. The configured read-only
Snowflake role remains the mutation boundary.

This is intentionally a relation-centric policy: unknown data-source shapes fail
closed, while ordinary expressions do not require inclusion in a recursive AST-node
allowlist. See [ADR 0019](decisions/0019-relation-centric-sql-authorization.md).

## 8. Submission, execution, and acceptance ordering

The central call path is:

```text
MCP or CLI adapter
└── ControlPlane.submit
    └── BackgroundQueryExecutor.submit
        ├── SnowflakeQueryAdmission.__call__
        │   └── policy.authorize(sql)                 synchronous rejection point
        ├── broker.submit(...)                        creates PENDING record
        └── schedule background _run task
            └── asyncio.to_thread(_execute)
                ├── acquire non-blocking one-query lock
                ├── request_cursor(...)
                │   ├── open connection
                │   └── create cursor
                ├── broker.register_cursor(...)
                ├── cursor.execute(governed_sql, timeout=60)
                ├── fetch and admit complete result
                ├── release private cursor association
                └── close cursor and connection
```

Connection or cursor failure becomes the request's coarse `failed` state. If
cancellation, expiry, or shutdown wins before cursor registration, the broker cancels
the late cursor instead of attaching it.

The Snowflake connector is synchronous, so `_execute` runs through
`asyncio.to_thread()`. `SnowflakeQueryAdmission` also owns a non-blocking thread lock as
an independent one-active-execution guard. The broker separately enforces one pending
request atomically.

## 9. Incremental Arrow retrieval and admission

[`_fetch_admitted_result()`](../src/snowglobe/snowflake_executor.py) consumes
`cursor.fetch_arrow_batches()` incrementally. Each connector table must be a PyArrow
table with the exact first-table schema, including metadata. It is converted only to
its own record batches.

If the iterator yields no table, `_empty_result_table()` uses public connector result
batch metadata to prove every batch has zero rows and recover the declared Arrow
schema. Empty results therefore remain typed rather than becoming schema-less success.

[`admit_record_batches()`](../src/snowglobe/arrow_stream.py) checks, as batches arrive:

- schema support and no more than 32 columns;
- cumulative rows no greater than 50;
- no variable-width cell larger than 16 KiB;
- cumulative decoded Arrow bytes no greater than 256 KiB; and
- cumulative serialized Arrow IPC bytes no greater than 256 KiB.

Variable cell size is measured from Arrow offset buffers, including sliced arrays. The
admission state serializes through a drainable PyArrow sink so serialized size is
measured incrementally. On success, the broker retains a tuple of admitted record
batches in `InMemoryArrowBatchSource`; it does not retain a concatenated table, rows,
or a file.

After `_execute` has returned and its context managers have closed resources, the
generic executor calls `broker.publish()`. Source attachment and transition to
`complete` happen atomically under the broker lock.

## 10. Broker lifecycle, cancellation, and expiry

[`InProcessBroker`](../src/snowglobe/broker.py) owns public lifecycle metadata and two
private associations: the active cursor while pending and the admitted Arrow source
while complete.

```text
PENDING ── publish admitted source ─────────────▶ COMPLETE
   │                                                 │
   ├── execution/admission error ──▶ FAILED          ├── expiry ──▶ EXPIRED
   ├── cancel ─────────────────────▶ CANCELLED       └── cancel ──▶ CANCELLED
   └── expiry ─────────────────────▶ EXPIRED
```

Important race behavior:

- Cursor registration is exact and one-time. A cursor created after any terminal
  transition is immediately cancelled rather than attached.
- Releasing a cursor removes only that exact object.
- Cancellation clears source and cursor under lock, then calls driver cancellation
  outside the lock. Driver cancellation failure is suppressed and never changes the
  closed public state.
- Cancellation is idempotent for an already-cancelled request and does not rewrite a
  failed request's terminal state.
- Expiry is refreshed during lookup/list/capacity checks and by an executor-owned
  expiry task. Expiry clears the source under lock and cancels an attached cursor only
  after releasing the broker lock.
- MCP and the viewer expose no cancellation command; broker cancellation remains an
  internal lifecycle and shutdown mechanism.

The broker stores `expires_at` for local lifecycle management and viewer display. MCP
does not disclose it.

## 11. Viewer backend and failure-atomic framing

[`result_api.py`](../src/snowglobe/result_api.py) exposes:

| Route | Purpose |
|---|---|
| `GET /healthz` | Value-free readiness |
| `GET /v1/requests` | Recent local request metadata |
| `GET /v1/requests/{id}` | One local request summary |
| `GET /v1/requests/{id}/stream` | Complete admitted Arrow result |

These are viewer routes, not MCP contracts. They may include `expires_at`, and the
stream contains result bytes. They are loopback-only but unauthenticated under the
single-analyst threat model.

Every route sets `Cache-Control: no-store`. The app factory requires explicit admission
limits, and streaming is available only when the request is currently complete with a
source.

The custom stream format is deliberately small:

```text
magic: "SNOWGLOBE-ARROW-STREAM" + version byte 0x01

frame header:
┌────────────┬───────────────────────────────┐
│ type: 1 B  │ payload length: 8 B, big-end  │
└────────────┴───────────────────────────────┘

type 1 = non-empty Arrow IPC payload
type 2 = completion, payload length must be zero
```

The backend serializes the already-admitted source under the transport byte ceiling.
Before every payload and before completion, it verifies that the broker still exposes
the same source object. Cancellation, expiry, overflow, iteration failure, or source
replacement makes the generator stop without a completion frame. Error details never
become stream payloads.

## 12. Browser ingestion and publication

The browser keeps result transport, parsing, and DuckDB inside a dedicated application
worker. The main thread handles lifecycle metadata and a bounded viewport:

```text
App.svelte
├── refresh or look up request metadata
├── explicit “Open result” action
├── replace a failed or closed one-result worker
└── worker.ts
    ├── send only the selected request ID to duckdb.worker.ts
    ├── correlate worker acknowledgements and viewport replies
    └── request one bounded viewport after publication

duckdb.worker.ts
├── instantiate in-memory DuckDB-Wasm
├── fetch the no-store framed result stream by request ID
├── ResultStreamParser validates framing and 256-KiB payload total
├── TransformStream provides ingestion backpressure
├── Apache Arrow reader parses incremental IPC
├── insert batches into _snowglobe_pending
├── on valid completion + clean EOF:
│   └── rename _snowglobe_pending to snowglobe_result
└── query at most viewport limit + 1 rows
```

[`ResultStreamParser`](../apps/viewer/src/result-stream.ts) accepts arbitrarily split
transport chunks, but rejects bad magic, unknown frame types, zero-length Arrow frames,
oversized declared frames, cumulative overflow, trailing bytes, truncated frames, and
missing completion. It also bounds buffered protocol bytes before copying an incoming
transport chunk.

[`createIncrementalArrowSink()`](../apps/viewer/src/arrow-ingest.ts) connects the
parser to Apache Arrow's async record-batch reader. The `TransformStream` writer
propagates reader backpressure to the worker's HTTP reader.

[`duckdb.worker.ts`](../apps/viewer/src/duckdb.worker.ts) uses a pending table so
partially parsed data is never queryable through the viewport path. Any parser,
ingestion, DuckDB, viewport, abort, or unexpected message failure closes the
connection, terminates DuckDB, reports `failed`, and closes the worker.

[`worker.ts`](../apps/viewer/src/worker.ts) permits one load per worker and correlates
reply types and sequences. The application worker owns and aborts its active HTTP
request during destruction. A second load attempt, stream error, browser worker error,
or viewer unmount destroys that worker. `App.svelte` creates a fresh worker after a load
failure or when the analyst closes a result, so another request can be opened.

Finally, [`createViewport()`](../apps/viewer/src/viewport.ts) converts only bounded
cells to strings, hex-encodes binary, uses ISO timestamps, preserves null, and enforces
the same 256-KiB text budget. Svelte escapes interpolated values and renders them as
text nodes, so HTML-like or prompt-like values remain inert.

## 13. Fixed MVP budgets

The source of truth is [`mvp_limits.py`](../src/snowglobe/mvp_limits.py), mirrored at
the browser boundary by [`mvp-limits.ts`](../apps/viewer/src/mvp-limits.ts).

| Budget | MVP value | Enforcement |
|---|---:|---|
| Pending requests | 1 | Broker and execution lock |
| Request TTL | 5 minutes | Broker and executor expiry task |
| Login timeout | 30 seconds | Connector arguments |
| Network timeout | 60 seconds | Connector arguments |
| Socket timeout | 15 seconds | Connector arguments |
| Statement timeout | 60 seconds | Session parameter and execute timeout |
| Queue timeout | 15 seconds | Session parameter |
| Rows | 50 admitted; SQL requests 51 | SQL policy and Arrow admission |
| Columns | 32 | Arrow schema admission |
| Variable-width cell | 16 KiB | Arrow offset-buffer inspection |
| Serialized Arrow | 256 KiB | Backend admission and browser parser |
| Decoded Arrow | 256 KiB | Backend admission |
| Main-thread viewport | 50 rows, 256 KiB | Worker query and viewport conversion |

Do not change one copy of a browser/backend shared budget without reviewing the other
boundary and adding evidence for the larger memory and rendering envelope.

## 14. Failure handling philosophy

MCP, the result-free CLI, and Pi sanitize failures into their closed receipts. Local
configuration, preflight, and startup commands instead preserve actionable diagnostics
for the analyst. Query execution failures still become only a coarse lifecycle state at
model-facing adapters.

| Failure point | MCP-visible result | Viewer/result behavior |
|---|---|---|
| Invalid tool shape | `INVALID_REQUEST` | No request |
| SQL policy rejection | `POLICY_REJECTED` | No Snowflake connection |
| Missing executor/startup failure | `SERVICE_UNAVAILABLE` | No published source |
| Driver, timeout, schema, or admission failure after acceptance | `failed` | No stream |
| Cancellation | `cancelled` | Source removed; incomplete stream has no completion frame |
| Expiry | `expired` | Source removed; active cursor cancelled |
| Unknown ID | `not_found` | Viewer returns fixed 404 body |
| Browser parse/ingestion failure | No new MCP data | Entire DuckDB worker is destroyed |

Do not log result batches, values, or result locations. `request_cursor()` suppresses
the Snowflake connector logger because its debug and exceptional paths can include SQL,
signed URLs, response structures, or Arrow payloads. This targeted suppression does not
require unrelated local startup errors to be detail-free. Snowglobe's own diagnostic
deliberately prints only the exact governed SQL and opaque request ID; accepted
submission receipts return the same pair. Operators must treat terminal and
model-harness captures as sensitive because SQL may contain literals.

## 15. Tests as architecture evidence

The tests are organized around boundaries rather than only functions:

| What to review | Best evidence |
|---|---|
| Exact MCP capabilities, schemas, parity, sanitization, HTTP round trip | [`test_mcp_gateway.py`](../tests/test_mcp_gateway.py) |
| Pi tool registration, receipt validation, stdin, process bounds, failures | [`integrations/pi/extensions`](../integrations/pi/extensions) |
| Pi root-manifest extension discovery | [`package-smoke.test.mjs`](../integrations/pi/package-smoke.test.mjs) |
| Lifecycle races, cursor identity, cancellation, expiry, capacity | [`test_broker.py`](../tests/test_broker.py) |
| Acceptance ordering and generic background cleanup | [`test_executor.py`](../tests/test_executor.py) |
| Hostile SQL and generated-SQL round trip | [`test_sql_policy.py`](../tests/test_sql_policy.py) |
| Connector ordering, empty schema, overflow, cancellation, no-connect rejection | [`test_snowflake_executor.py`](../tests/test_snowflake_executor.py) |
| Incremental schema/cell/row/byte admission | [`test_arrow_stream.py`](../tests/test_arrow_stream.py) |
| Viewer routes, headers, frames, incomplete stream, cancellation mid-stream | [`test_result_api.py`](../tests/test_result_api.py) |
| Result-canary presence in the viewer path and absence from MCP | [`test_boundary_canaries.py`](../tests/test_boundary_canaries.py) |
| Browser framing and terminal publication | [`result-stream.test.ts`](../apps/viewer/src/result-stream.test.ts) |
| Incremental Arrow ingestion | [`arrow-ingest.test.ts`](../apps/viewer/src/arrow-ingest.test.ts) |
| Worker destruction and one-result lifecycle | [`worker.test.ts`](../apps/viewer/src/worker.test.ts) |
| Bounded viewport conversion | [`viewport.test.ts`](../apps/viewer/src/viewport.test.ts) |

Run everything with:

```bash
./scripts/check-dev.sh
```

Useful focused loops:

```bash
uv run pytest tests/test_sql_policy.py
uv run pytest tests/test_snowflake_executor.py tests/test_arrow_stream.py
uv run pytest tests/test_mcp_gateway.py tests/test_boundary_canaries.py
npm test -- src/result-stream.test.ts
npm test -- src/worker.test.ts
npm run test:pi
```

## 16. A practical code-review order

To rebuild context quickly, review in this order:

### Pass 1: product and threat boundary

1. [README.md](../README.md)
2. [SECURITY.md](../SECURITY.md)
3. [PLAN.md](../PLAN.md), especially the MVP target and deferred work
4. [ADR 0008](decisions/0008-single-analyst-loopback-runtime.md) through
   [ADR 0018](decisions/0018-minimal-boundary-cleanup.md)

You should finish this pass able to state what MCP, CLI, and Pi tool output may
disclose and why the viewer is not an authentication boundary.

### Pass 2: model-facing surface

1. [`contracts.py`](../src/snowglobe/contracts.py)
2. [`control.py`](../src/snowglobe/control.py)
3. [`mcp_gateway.py`](../src/snowglobe/mcp_gateway.py)
4. [`cli.py`](../src/snowglobe/cli.py)
5. [`integrations/pi/extensions`](../integrations/pi/extensions)
6. [`test_mcp_gateway.py`](../tests/test_mcp_gateway.py)
7. [`test_cli.py`](../tests/test_cli.py)
8. [`test_boundary_canaries.py`](../tests/test_boundary_canaries.py)

Check exact fields, text/structured equivalence, malformed calls, and exception
sanitization before reading implementation internals.

### Pass 3: authorization and execution

1. [`configuration.py`](../src/snowglobe/configuration.py)
2. [`sql_policy.py`](../src/snowglobe/sql_policy.py)
3. [`executor.py`](../src/snowglobe/executor.py)
4. [`snowflake_executor.py`](../src/snowglobe/snowflake_executor.py)
5. [`broker.py`](../src/snowglobe/broker.py)

Trace one success, one policy rejection, one cancellation race, and one overflow. The
key review question is always: **what is already registered, controllable, admitted,
or cleaned up at the moment a public state changes?**

### Pass 4: result data plane

1. [`arrow_stream.py`](../src/snowglobe/arrow_stream.py)
2. [`result_api.py`](../src/snowglobe/result_api.py)
3. [`result-stream.ts`](../apps/viewer/src/result-stream.ts)
4. [`arrow-ingest.ts`](../apps/viewer/src/arrow-ingest.ts)
5. [`duckdb.worker.ts`](../apps/viewer/src/duckdb.worker.ts)
6. [`worker.ts`](../apps/viewer/src/worker.ts)
7. [`viewport.ts`](../apps/viewer/src/viewport.ts)
8. [`App.svelte`](../apps/viewer/src/App.svelte)

Follow the same bytes from Snowflake table to record batch, admitted source, framed
HTTP payload, provisional table, published table, bounded viewport, and escaped Svelte
text.

### Pass 5: proof and current gaps

Run `./scripts/check-dev.sh`, then read the unchecked Gate 5 items and deferred section in
[PLAN.md](../PLAN.md). This distinguishes implementation-complete behavior from
connected behavior that still needs evidence.

## 17. Change-impact checklist

Use this as a map, not a substitute for threat modeling:

| If changing… | Review together… | Minimum focused checks |
|---|---|---|
| MCP fields, tools, status, or errors | contracts, gateway, PLAN model-visible contracts | MCP gateway + boundary canaries + real Streamable HTTP round trip |
| Pi tools, process handling, or package API | CLI, Pi contracts, extension, ADR 0014 | Pi typecheck + Pi tests + package-load smoke test |
| SQL grammar or SQLGlot version | policy, ADR 0019, allowed views, generated-SQL pass, row-cap semantics | SQL policy tests |
| Connector settings or lifecycle | configuration, Snowflake context manager, executor, ADRs 0009/0011 | configuration + Snowflake + executor tests |
| Cancellation, expiry, concurrency | broker and generic executor | broker race tests + Snowflake cancellation tests |
| Arrow types or limits | backend admission, stream replay, browser parser/ingestion, viewport | Arrow + Result API + all viewer tests |
| Stream framing | Python writer and TypeScript parser together | Result API + result-stream + canary tests |
| Browser workers | worker, DuckDB, Vite | worker tests + build |
| Network binding or deployment | launcher, Vite, SECURITY, ADR 0008 | local-server tests and listener inspection |

Consequential security or architecture changes require a new ADR and an update to the
decision index. Do not rewrite the retained [`architecture-proposal.md`](architecture-proposal.md)
to make it appear current.

## 18. Current MVP limitations

The implementation intentionally does not provide:

- connected Snowflake release evidence yet;
- production credentials, sensitive data, or routine analyst use;
- more than one pending request;
- restart-durable requests or results;
- viewer authentication or same-host process isolation;
- results larger than 50 rows or 256 KiB;
- pagination, sorting, filtering, projection, charts, or virtualization;
- export, clipboard-all, uploads, external readers, persistence, or telemetry; or
- remote hosting, sharing, accounts, tenants, or multi-user authorization.

The authoritative current/deferred split is in [PLAN.md](../PLAN.md). The older
[`architecture-proposal.md`](architecture-proposal.md) is retained source material and
contains ideas—such as enterprise authentication and a separate Result API—that were
superseded by later ADRs.

## 19. Glossary

- **Admission:** Proving work or data satisfies policy and fixed limits before making
  it publicly available.
- **Broker:** The process-local state machine that correlates an opaque request ID with
  lifecycle, a private active cursor, or a complete admitted source.
- **Control plane:** MCP submission and lifecycle polling; no result-derived data.
- **Data plane:** Loopback viewer routes and browser worker carrying admitted result
  bytes.
- **Failure-atomic publication:** Partial work remains private and is discarded unless
  an explicit terminal condition proves the whole operation succeeded.
- **Governed SQL:** SQL regenerated from an AST that passed Snowglobe's recursive
  policy and received the server-owned overflow cap.
- **Opaque request ID:** A random correlator with no Snowflake identifier, SQL, or
  secret meaning.
- **Provisional table:** The worker's `_snowglobe_pending` DuckDB table, which is not
  exposed to viewport queries before clean stream completion.
