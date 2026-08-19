# Snowglobe implementation plan

**Status:** Gates 1–4 are complete; the constrained connected MVP procedure is next
**Last updated:** August 19, 2026
**Current decision:** [ADR 0011](docs/decisions/0011-bounded-snowflake-execution.md)
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

The MVP intentionally uses an ephemeral in-process broker and loses requests on
restart. This is acceptable only for the constrained test environment defined below,
with short statement timeouts, detached-query controls, explicit cancellation, and
documented restart behavior. Local restart durability is deferred; it must not be
solved by introducing multi-user infrastructure.

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

## 5. MVP target

The next release target is a **test-environment MVP**, not a feature-complete analyst
application. It proves one real path:

> Submit one governed read query through MCP, poll an opaque ID, execute it with a
> fixed least-privileged Snowflake profile, and inspect a bounded result in the local
> viewer without result-derived information crossing the MCP boundary.

The existing 50-row/256-KiB bounded viewport is sufficient for this MVP because the
MVP admission budgets must not permit a result larger than that viewer can inspect.
Pagination, sorting, filtering, charts, virtualization, durable requests, export, and
polished packaging do not block the real Snowflake test.

### Required Snowflake test environment

The first connected environment must use:

- a dedicated non-production account or isolated test role and only non-sensitive
  canary data;
- read access only to explicitly allowlisted test databases, schemas, and views;
- a small dedicated warehouse with an administrator-owned resource monitor;
- a dedicated local key/profile that cannot assume a broader role;
- no production credentials, production datasets, or sensitive data; and
- an operator who can independently inspect Snowflake query history, cancellation,
  warehouse usage, and grants during the test.

`SECURITY.md` continues to prohibit Snowflake credentials until every mandatory gate
below is complete and the document is updated with the constrained test procedure.

## 6. MVP delivery plan

Items are ordered. Real credentials must not be configured in Snowglobe, and no real
connection may be attempted, until Gates 1–4 are complete and `SECURITY.md` has been
updated for the Gate 5 procedure.

### Already complete — reusable foundation

- [x] Record the low-level MCP, SQLGlot, Snowflake connector, Arrow, React, and
  DuckDB-Wasm architecture.
- [x] Implement strict `connections.toml` loading, explicit connector arguments, and
  PEM/DER RSA key conversion.
- [x] Implement the closed submission and lifecycle contracts, opaque IDs, local
  broker, and atomic synthetic background-executor seam.
- [x] Implement the shared loopback-only MCP/viewer launcher.
- [x] Implement request-scoped connection/cursor ownership and idempotent cancellation.
- [x] Implement incremental Arrow admission, failure-atomic framing, provisional
  DuckDB-Wasm ingestion, and a bounded escaped viewport.

### Gate 1 — connection and resource safety

- [x] Reject unsafe local config/private-key ownership or permissions and document the
  supported permission policy.
- [x] Define fixed MVP limits for statement, queue, login, network, request expiry,
  rows, columns, cell bytes, Arrow bytes, decoded bytes, and browser result input; cap
  the admitted result at no more than the existing 50-row/256-KiB viewer capacity.
- [x] Configure detached-query behavior so disconnect/restart does not intentionally
  leave unbounded work running; retain a short statement timeout as the backstop.
- [x] Enforce one active Snowflake request per runtime for the MVP.
- [x] Implement a value-free preflight command for local profile/key validation and an
  explicitly enabled, result-free connection check. Gate 5 independently verifies
  role grants, allowlisted objects, warehouse, and resource monitor configuration.

Why this gate cannot be deferred: without it, a test can leak credentials, create
orphaned work, overload the local process, or incur uncontrolled Snowflake cost before
SQL and result handling are exercised.

### Gate 2 — minimum SQL authorization policy

- [x] Parse with SQLGlot's Snowflake dialect and accept exactly one `SELECT` or
  `WITH … SELECT` statement.
- [x] Recursively reject every unsupported AST node, including DDL, DML, calls,
  scripting, dynamic SQL, stages, file transfer, external/network functions, and
  unapproved UDFs.
- [x] Require references to resolve only to configured database/schema/view and
  function allowlists (empty for the MVP); reject ambiguous or incompletely qualified
  references when they cannot be proven safe.
- [x] Keep role, warehouse, database, profile, authenticator, and key path entirely
  server-owned and unavailable as tool inputs.
- [x] Apply and verify a semantics-preserving server-owned `K + 1` row cap so an
  oversized result is detected rather than silently truncated.
- [x] Port the hostile Querido fixtures and add Snowflake-specific attacks covering
  comments, quoting, nested CTEs/subqueries, multiple statements, stages, dangerous
  functions, and dialect round trips.

Why this gate cannot be deferred: a parser alone does not prevent mutation, policy
escape, external access, or execution against unintended objects. The least-privileged
Snowflake role is an independent backstop, not a replacement for this policy.

### Gate 3 — real asynchronous Snowflake executor

- [x] Connect configured work to the existing background-executor seam and establish
  pending registration plus request-scoped cursor ownership before returning
  `accepted`.
- [x] Execute the policy-approved, server-capped SQL with the reviewed timeout and
  session settings from Gate 1.
- [x] Adapt `fetch_arrow_batches()` to the existing `ArrowBatchSource` contract and
  retrieve incrementally with backpressure.
- [x] Preserve Arrow names/types and define the admitted empty-result schema and
  completion behavior.
- [x] Enforce all compute and result limits before browser publication; reject
  oversized results without silent truncation or local spill.
- [x] Never concatenate complete results, call `to_pylist()`, build full row
  dictionaries, use `fetchall()`, or write result bytes to an agent-visible file.
- [x] Map execution, driver, cancellation, timeout, overflow, and cleanup failures to
  value-free lifecycle states; never expose Snowflake IDs, SQL, credentials, tokens,
  or driver errors through MCP or ordinary logs.
- [x] Close the cursor and connection and remove private broker associations on every
  terminal path; make cancellation and expiry race-safe.

Why this gate cannot be deferred: this is the missing production-shaped seam. A
partially connected executor could return acceptance before work is controllable,
retain credentials or handles, publish incomplete data, or bypass admission limits.

### Gate 4 — minimum browser and boundary assurance

- [x] Destroy application-worker and DuckDB state on every stream error, overflow,
  cancellation, expiry, request change, and viewer close path.
- [x] Complete no-IndexedDB, no-OPFS, no-service-worker-cache, no automatic-restore,
  and no-external-reader tests.
- [x] Seed non-sensitive canaries in values, column names, SQL, internal errors,
  Unicode, binary, empty results, multiple batches, and oversized cells/results.
- [x] Capture MCP traffic, stdout/stderr, ordinary logs, URLs, public errors, and
  browser storage; assert canaries appear only in the local viewer data path.
- [x] Verify every pending and terminal MCP response contains only the closed receipt,
  with no rows, schema, counts, sizes, timing, Snowflake identifiers, or errors.
- [x] Verify the supported launcher and Vite server are loopback-only.

Why this gate cannot be deferred: the MVP's primary security claim is channel
separation. A successful query is not sufficient evidence if values can leak through
MCP, logs, errors, URLs, browser persistence, or provisional worker state.

### Gate 5 — connected MVP test and release evidence

- [ ] Document exact setup, launch, shutdown, cancellation, expiry, and restart steps
  for the constrained Snowflake test environment.
- [ ] Update `SECURITY.md` from “no credentials” to permit only the documented MVP
  test configuration once Gates 1–4 pass.
- [ ] Configure the dedicated test profile and run the value-free preflight;
  independently verify its role grants, allowlisted objects, warehouse, and resource
  monitor.
- [ ] In the constrained environment, verify an allowed query from submit → pending →
  complete → viewer and confirm its canary values appear only in the viewer.
- [ ] Verify policy rejection before Snowflake execution for mutation, multiple
  statements, disallowed objects/functions, stage access, and tool-selected config.
- [ ] Verify empty, multi-batch, oversized, timeout, cancellation, driver-failure,
  expiry, and process-restart behavior while inspecting Snowflake query history and
  warehouse usage independently.
- [ ] Run the complete Python, MCP, connector, stream, browser, build, and boundary
  suites and retain value-free pass/fail evidence.

MVP exit criteria: one bounded real result completes the local viewer journey; unsafe
SQL never executes; timeout, cancellation, overflow, and restart are bounded and
documented; credentials and result-derived information remain absent from MCP and
ordinary outputs; and the Snowflake role independently lacks mutation and unintended
object access.

## 7. Deferred until after the connected MVP

These items improve usefulness, resilience, or distribution but do not add evidence
needed for the first constrained Snowflake test:

### Viewer analysis and scale

- [ ] Add deterministic DuckDB pagination, projection, sorting, and filtering.
- [ ] Add one bounded aggregate chart.
- [ ] Virtualize visible rows/columns with bounded, cancellable columnar caches.
- [ ] Return chart aggregates sized to display pixels rather than source cardinality.
- [ ] Benchmark wide strings, nulls, large cells, sorting, aggregation, and rapid
  scrolling.

### Durability and lifecycle convenience

- [ ] Decide on and implement local restart-durable request state and private
  retrieval handles.
- [ ] Add automatic restoration only if a later persistence decision explicitly
  changes the current ephemeral-browser boundary.
- [ ] Add richer value-free operational diagnostics after the minimum boundary suite
  establishes which metadata is safe.

### Packaging and broader hardening

- [ ] Package a polished local launcher and viewer distribution; the supported
  loopback development launcher is sufficient for the MVP test.
- [ ] Document key rotation and backup behavior beyond the minimum setup/restart
  runbook.
- [ ] Expand performance and memory testing beyond the fixed MVP budgets.
- [ ] Revisit export, copy-all, uploads, external readers, remote hosting, sharing, or
  multi-user operation only through new security decisions and threat models.

## 8. MVP deferral risks

| Deferred capability | Risk accepted for MVP | MVP constraint or mitigation | Trigger to implement |
|---|---|---|---|
| Restart-durable requests | A process restart loses local request IDs and results; an abruptly disconnected Snowflake query may remain visible briefly until server controls stop it | Non-production data, one active request, short statement timeout, detached-query controls, explicit shutdown/cancellation test | Before routine analyst use where restart recovery matters |
| Pagination, sort, filter, and projection | Results larger than one bounded viewport must be rejected, limiting useful analysis | Cap admitted MVP results to the existing 50-row/256-KiB viewer capacity; never show a silently incomplete result | Immediately after the connected path is proven |
| Charts and aggregate exploration | The viewer is a validation surface rather than a useful BI experience | Validate raw bounded rows only | After table navigation works |
| Full virtualization and broad benchmarks | Results near admitted limits may render slowly or use more memory than desired | Conservative fixed MVP row/byte/memory limits and small test datasets | Before increasing limits or using representative workloads |
| Polished packaging | Setup is manual and easier to misconfigure | One documented launcher and exact preflight procedure; loopback binding remains mandatory | Before distribution to another analyst |
| Rich diagnostics | Failures may be harder to diagnose | Fixed lifecycle states, independent Snowflake history, and value-free test evidence | After safe diagnostic fields are explicitly reviewed |

The following are **not accepted deferral risks** and remain MVP blockers: SQL AST
authorization, least-privileged Snowflake grants, explicit timeouts and resource
limits, incremental Arrow admission, failure-atomic browser publication, terminal
cleanup, loopback binding, no browser persistence, and proof that MCP/log/error
channels remain result-free.

## 9. Test strategy

| Layer | MVP evidence |
|---|---|
| MCP | exact two-tool capabilities, schema closure, text/structured parity, malformed/unknown-call sanitization, canary absence |
| Lifecycle | pending and every terminal state; unknown IDs; expiry; race-safe idempotent cancellation |
| Config/key | strict TOML shape, profile selection, safe permissions, PEM/DER conversion, secret-safe failures |
| SQL policy | allowlisted reads plus comments, quoting, nested CTEs, multiple statements, stages, dangerous functions, and dialect round trips |
| Connector | exact kwargs/session settings, one active request, per-request cleanup, timeout/cancellation, incremental Arrow |
| Stream | real multi-batch and empty results, admission counters, backpressure, overflow, failure-atomic completion |
| Browser | lookup by ID, escaping, provisional publication, bounded viewport, terminal destruction, no persistence |
| Local runtime | one shared broker, loopback-only hosts, restart and shutdown behavior |
| Boundary | viewer-visible canary absent from MCP, process output, URLs, errors, and browser storage |
| Snowflake | read-only grants, object restrictions, resource monitor, query history, cancellation, and bounded warehouse use |

## 10. Non-goals

- viewer authentication, OIDC, accounts, tenants, cross-user authorization, or sharing;
- hosted or remotely exposed MCP/viewer services;
- letting the model read or summarize result rows;
- returning schema, counts, previews, errors, Snowflake IDs, or links through MCP;
- general Snowflake administration, mutation, procedures, stages, or file transfer;
- a generic SQL IDE, notebook, or BI replacement;
- durable browser datasets, offline use, automatic restoration, or third-party telemetry;
- export or copy-all in the initial product; and
- adversarial isolation from other processes running as the analyst.

## 11. Definition of done

The connected MVP is done when evidence supports this statement in the constrained
Snowflake test environment:

> One analyst can submit a governed Snowflake read query asynchronously, receive and
> poll an opaque request ID through MCP, and use that ID to inspect the complete result
> in a loopback-only local viewer. The SQL policy and least-privileged role prevent
> mutation and unintended object access. MCP emits only its closed receipt and
> lifecycle contracts; result values, schema, sizes, Snowflake identifiers, and errors
> remain out of MCP and ordinary logs. Result ingestion and browser analysis remain
> bounded and ephemeral.

This definition does not require durable requests, advanced table navigation, charts,
virtualization, export, or polished packaging.

## 12. Immediate next items

Gates 1–4 are complete. Document Gate 5's exact constrained-environment setup,
operation, cancellation, expiry, restart, and evidence procedure next, then update
`SECURITY.md` to permit only that procedure. Do not configure real credentials or
attempt a Snowflake connection before those documentation steps are complete.
