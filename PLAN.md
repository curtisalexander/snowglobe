# Snowglobe implementation plan

**Status:** Migrated to a single-analyst loopback architecture; synthetic lifecycle and viewer paths exist, governed Snowflake execution does not
**Last updated:** August 19, 2026
**Current decision:** [ADR 0008](docs/decisions/0008-single-analyst-loopback-runtime.md)
**Retained source proposal:** [architecture-proposal.md](docs/architecture-proposal.md)

## 1. Outcome

Build a local tool for one Snowflake analyst:

1. the analyst asks a coding agent to draft and submit one governed read query;
2. Snowglobe starts it asynchronously and MCP returns an opaque request ID;
3. the agent may poll that ID for a coarse lifecycle state only;
4. the analyst opens the local viewer and selects or pastes the same ID;
5. the viewer backend streams a complete, admitted Arrow result;
6. a dedicated worker loads it into in-memory DuckDB-Wasm; and
7. the analyst explores bounded table, filter, sort, aggregate, and chart views.

Snowglobe is an individual local application. It is not a shared MCP service, hosted
result service, tenant platform, or enterprise identity product.

## 2. Product boundary

### MCP may disclose

- submission `status`: `accepted` or `rejected`;
- one random opaque `request_id`;
- a fixed submission `reason_code`; and
- lifecycle `status`: `pending`, `complete`, `failed`, `cancelled`, `expired`,
  `not_found`, or `service_unavailable`.

### MCP must not disclose

- rows, values, schema, column names, or types;
- row counts, result sizes, whether rows exist, or progress percentages;
- query duration or result-dependent timing metadata;
- Snowflake query IDs, result tokens, or result URLs;
- SQL, database/parser/driver errors, or policy details beyond fixed reasons; or
- images, charts, resources, downloads, or other result-derived artifacts.

Result bytes travel only from the local viewer backend to the browser worker. The
viewer backend is the former “Result API”; in this design it is simply a set of local
routes in the same process as MCP and the broker.

### Explicit limitation

Loopback binding is not viewer authentication or same-host process isolation. A coding
agent with arbitrary local HTTP, browser, shell, screenshot, accessibility, or process
access may be able to read the viewer. The guarantee is that Snowglobe creates no
automatic result-bearing MCP response—not that it protects data from software running
as the analyst.

## 3. Accepted architecture

| Area | Decision |
|---|---|
| User model | One analyst, one local OS security context |
| Service exposure | Loopback only; supported launcher binds `127.0.0.1` |
| Runtime | One process owns MCP routes, viewer routes, and broker |
| MCP tools | `submit_read_query` and `get_query_status` |
| Correlation | Random 20–32 character request ID; not a Snowflake ID or secret |
| Async lifecycle | Pending record before execution; terminal complete/failed/cancelled/expired state |
| Viewer discovery | List recent local requests or paste the MCP request ID |
| Viewer data | Complete, admitted Arrow stream; no result bytes through MCP |
| Browser analytics | In-memory DuckDB-Wasm in a dedicated application worker |
| Browser persistence | No IndexedDB, OPFS, service-worker result cache, or automatic restoration |
| SQL | One Snowflake `SELECT` or `WITH … SELECT` AST; deny everything else |
| Snowflake config | Local `connections.toml`; fixed profile, role, warehouse, database, authenticator, and key path |
| Admission | Independent compute, row, column, cell, Arrow-byte, and memory limits |
| Oversized results | Reject; never silently truncate or spill into browser storage |
| Initial exclusions | Viewer auth, accounts, sharing, export, remote hosting, tenants, uploads, external DuckDB readers, telemetry |

The in-process broker intentionally loses requests on restart. Before real use, choose
either that explicit ephemeral behavior or a small local persistence mechanism for
request lifecycle and private Snowflake retrieval handles. Do not solve restart
durability by introducing multi-user infrastructure.

## 4. Model-visible contracts

Submission receipt:

```json
{
  "status": "accepted",
  "request_id": "01JABCDEFGHJKMNPQRSTVWXYZ",
  "reason_code": "NONE"
}
```

Lifecycle receipt:

```json
{
  "request_id": "01JABCDEFGHJKMNPQRSTVWXYZ",
  "status": "pending"
}
```

Rules:

- both schemas set `additionalProperties: false`;
- text and structured MCP content represent exactly the same fields;
- accepted means policy admission and asynchronous registration succeeded, not that
  the query completed or returned rows;
- invalid submission never reflects input and uses `INVALID_REQUEST`,
  `POLICY_REJECTED`, or `SERVICE_UNAVAILABLE`;
- malformed status input is not reflected;
- unknown IDs return `not_found` with no further detail;
- internal query and driver failures return only `failed`; and
- MCP advertises tools only, with no resources or prompts.

## 5. Delivery milestones

### Milestone 0 — foundation and architecture

- [x] Record Python, low-level MCP, SQLGlot, React, Arrow, and DuckDB-Wasm choices.
- [x] Implement strict `connections.toml` loading and PEM/DER RSA key conversion.
- [x] Pin and audit the narrow Querido reuse baseline.
- [x] Define incremental Arrow admission and failure-atomic stream framing.
- [x] Pivot identity and deployment decisions to one local analyst in ADR 0008.
- [x] Replace viewer authentication/ownership with a local lifecycle broker.
- [x] Add one loopback launcher for MCP and viewer routes sharing that broker.
- [ ] Define local config/key permission policy.
- [ ] Decide ephemeral-only versus restart-durable local request state.

### Milestone 1 — synthetic local vertical slice

#### MCP and lifecycle

- [x] Implement closed `submit_read_query` shell; keep it fail-closed.
- [x] Implement closed `get_query_status` lifecycle polling.
- [x] Generate opaque IDs with no embedded SQL, identity, or Snowflake identifier.
- [x] Model pending, complete, failed, cancelled, and expired states.
- [x] Sanitize malformed calls and unexpected exceptions.
- [x] Verify exact capabilities and a real Streamable HTTP round trip.
- [ ] Connect synthetic submission to a background executor as one atomic accepted path.
- [ ] Prove values and internal errors remain absent from process output around execution.

#### Local viewer backend and browser

- [x] List recent local requests and look one up by opaque ID.
- [x] Allow Arrow streaming only for complete requests.
- [x] Enforce row, column, cell, serialized-byte, and decoded-byte limits.
- [x] Omit terminal completion on source error, cancellation, expiry, or overflow.
- [x] Ingest provisionally into in-memory DuckDB-Wasm and publish only on completion.
- [x] Render one 50-row/256-KiB bounded viewport with escaped cells.
- [ ] Destroy worker/database state on every error, expiry, cancellation, and close path.
- [ ] Add deterministic DuckDB pagination, projection, sorting, and filtering.
- [ ] Add one bounded aggregate chart.
- [ ] Complete browser no-persistence and no-external-reader tests.

#### Boundary harness

- [ ] Seed canaries in values, column names, SQL, errors, Unicode, binary, and oversized cells.
- [ ] Capture MCP traffic, stdout/stderr, logs, URLs, errors, and browser storage.
- [ ] Assert canaries are visible in the local viewer and absent from MCP and persistence channels.
- [ ] Verify pending/terminal status reveals no rows, schema, counts, sizes, timing,
  Snowflake identifiers, or errors.
- [x] Verify the supported launcher and Vite server are loopback-only.

Exit criteria: the synthetic submit → poll → paste/list ID → view journey works in one
local runtime, incomplete data never publishes, and no complete dataset becomes a
JavaScript row store.

### Milestone 2 — governed asynchronous Snowflake execution

#### SQL policy

- [ ] Accept exactly one parsed `SELECT` or `WITH … SELECT` statement.
- [ ] Recursively deny DDL, DML, calls, scripting, dynamic SQL, stages, file transfer,
  external/network functions, and unapproved UDFs.
- [ ] Allowlist approved databases, schemas, views, and functions.
- [ ] Deny tool-selected role, warehouse, profile, authenticator, key path, and database.
- [ ] Apply a semantics-preserving server `K + 1` cap.
- [ ] Port hostile Querido fixtures and add Snowflake-specific AST attacks.

#### Connection and execution

- [ ] Build Snowflake connector arguments from the explicit configuration allowlist.
- [ ] Add reviewed statement, queue, login, network, and detached-query settings.
- [ ] Start execution asynchronously and register request/cursor before returning accepted.
- [ ] Keep Snowflake query IDs, credentials, tokens, and driver errors private.
- [ ] Use one request-scoped cursor and idempotent cancellation; never cancel all cursors.
- [ ] Retrieve `fetch_arrow_batches()` incrementally with backpressure.
- [ ] Never concatenate full results, call `to_pylist()`, build full row dictionaries,
  fall back to `fetchall()`, or place result bytes in a local agent-visible file.
- [ ] Preserve Arrow names/types and an empty-result schema/completion contract.
- [ ] Enforce compute and result limits before complete publication.
- [ ] Transition to `failed` without exposing the failure through MCP.
- [ ] Expire and clean up request associations and Snowflake handles.

Exit criteria: the least-privileged Snowflake role cannot mutate or escape policy;
bounded real results complete the same local viewer journey; expensive and oversized
queries stop independently; and all MCP canary tests remain green.

### Milestone 3 — useful bounded analysis

- [ ] Virtualize the table and query only visible rows/columns plus bounded overscan.
- [ ] Normalize viewer filters, sorts, and projections into parameterized local SQL.
- [ ] Keep viewport caches columnar, byte-bounded, and cancellable.
- [ ] Return chart aggregates sized to display pixels, not source cardinality.
- [ ] Benchmark strings, nulls, wide cells, sorting, aggregation, and rapid scrolling.
- [ ] Confirm values never enter route state, titles, notifications, telemetry, or
  persistence.

### Milestone 4 — individual-use hardening

- [ ] Package one local launcher and viewer distribution with loopback defaults.
- [ ] Add a single-runtime concurrency cap and value-free operational diagnostics.
- [ ] Document key rotation, cancellation, expiry, cleanup, backup, and restart behavior.
- [ ] Verify no LAN/public binding in supported startup paths.
- [ ] Run the complete canary, SQL-policy, connector, stream, browser, and memory suite.

## 6. Test strategy

| Layer | Primary evidence |
|---|---|
| MCP | exact two-tool capabilities, schema closure, text/structured parity, sanitization |
| Lifecycle | pending and every terminal state; unknown IDs; expiry; idempotent cancellation |
| Config/key | strict TOML shape, profile selection, PEM/DER conversion, secret-safe failures |
| SQL policy | comments, quoting, CTE writes, multiple statements, stages, dangerous functions |
| Connector | explicit kwargs, per-request cursor cleanup, async transition, incremental Arrow |
| Stream | admission counters, backpressure, truncation, cancellation, overflow, completion marker |
| Browser | lookup by ID, escaping, provisional publication, bounded viewport, no persistence |
| Local runtime | MCP and viewer share one broker; supported host bindings are loopback |
| Boundary | result canary visible in viewer and absent from MCP/output/storage |

## 7. Non-goals

- viewer authentication, OIDC, accounts, tenants, cross-user authorization, or sharing;
- hosted or remotely exposed MCP/viewer services;
- letting the model read or summarize result rows;
- returning schema, counts, previews, errors, Snowflake IDs, or links through MCP;
- general Snowflake administration, mutation, procedures, stages, or file transfer;
- a generic SQL IDE, notebook, or BI replacement;
- durable browser datasets, offline use, automatic restoration, or third-party telemetry;
- export or copy-all in the initial product; and
- adversarial isolation from other processes running as the analyst.

## 8. Definition of done

The initial product is done when evidence supports this statement:

> One analyst can submit a governed Snowflake read query asynchronously, receive and
> poll an opaque request ID through MCP, and use that ID to inspect the complete result
> in a loopback-only local viewer. MCP emits only its closed receipt and lifecycle
> contracts; result values, schema, sizes, Snowflake identifiers, and errors remain out
> of MCP and ordinary logs. Result ingestion and browser analysis remain bounded and
> ephemeral.

## 9. Immediate next item

The architecture migration is complete when its checks pass. The next implementation
item is the **governed asynchronous Snowflake executor seam**:

1. define and test explicit connector arguments from `connections.toml`;
2. own one connection/cursor lifecycle per request;
3. submit work in the background and atomically publish a pending broker record before
   returning `accepted`;
4. transition only to closed lifecycle states through MCP; and
5. expose incremental Arrow only to the local viewer after admission.

Do not connect acceptance to real Snowflake until SQL AST policy and execution limits
are enforced in the same path.
