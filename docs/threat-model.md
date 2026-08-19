# Single-analyst local threat model

**Status:** Synthetic proof
**Last updated:** August 19, 2026

## Scope and claim

One analyst runs Snowglobe and a coding agent on one machine. The analyst's configured
Snowflake identity determines warehouse access. The coding agent supplies SQL through
MCP; the analyst reviews completed results in the local viewer.

The claim is narrow: Snowglobe's MCP output contains only the closed submission and
lifecycle contracts in `PLAN.md`. Query-result bytes and rich metadata do not travel
through MCP. The local viewer backend is a separate application path, but it is not
protected from other processes running as the analyst.

## Components and allowed data

| Component | Data allowed | Main controls |
|---|---|---|
| Coding agent and MCP client | Submitted SQL, purpose, TTL, opaque request ID, fixed reason, coarse lifecycle | Closed schemas, sanitized exceptions, no MCP resources/prompts/result reader |
| Local Snowglobe runtime | Query input, policy decision, private execution handle, opaque ID, lifecycle, expiry | One loopback process, value-free logs, request-scoped cleanup |
| Snowflake | Governed SQL and configured credentials | Explicit connector arguments, least-privileged role, AST policy, independent limits |
| Local viewer backend | Request lifecycle and admitted Arrow result | Loopback binding, no-store/security headers, stream only complete requests |
| Browser worker | Provisional Arrow and in-memory DuckDB-Wasm table | Failure-atomic publication, memory limits, termination on failure |
| Browser main thread | Request list and bounded viewport/aggregate responses | Escaped rendering, no persistence/telemetry, bounded copies |

## Trust boundary

```text
┌──────────────────── analyst's local security context ────────────────────┐
│ coding agent ──MCP──▶ local runtime ──configured identity──▶ Snowflake   │
│                         │                                                │
│                         ├── process-local request broker                 │
│                         │                                                │
│ browser ◀──Arrow── local viewer backend                                 │
└──────────────────────────────────────────────────────────────────────────┘
```

The local operating-system user boundary is trusted. An attacker who can execute as
the analyst, read the browser, or control the coding-agent host is outside the product
boundary and may access viewer data. Loopback prevents ordinary remote clients from
connecting; it does not distinguish the browser from another local process.

## Primary threats and controls

| Threat | Control |
|---|---|
| Result values or errors leak through MCP | Closed result schemas; lifecycle-only polling; final exception sanitization; canary scans |
| Service is exposed to the network | Supported launcher and Vite bind to `127.0.0.1`; documentation forbids `0.0.0.0` |
| SQL mutates data or escapes approved objects | One Snowflake `SELECT` AST; object/function allowlists; fixed role/warehouse; least privilege |
| Expensive or oversized work exhausts resources | Statement/queue timeouts; concurrency cap; server row/column/cell/Arrow/memory limits |
| Partial stream is mistaken for a complete result | Terminal framing marker; provisional DuckDB table; destroy state if completion is absent |
| Data persists in browser or telemetry | No IndexedDB/OPFS/service-worker result cache; no third-party telemetry; `no-store` headers |
| Opaque ID exposes a Snowflake identifier or query | Random URL-safe ID with no embedded identity, SQL, or Snowflake ID |
| Separate backend processes lose request correlation | One supported runtime owns MCP, viewer routes, and process-local broker |

## Fail-closed rules

- Submission remains rejected until SQL policy, configured execution, broker
  registration, and asynchronous startup succeed as one path.
- Status polling emits only the request ID and allowlisted lifecycle state.
- Unknown IDs and internal failures reveal no query, source, error, or result detail.
- Only complete, unexpired requests have a stream source.
- Arrow stays provisional until all limits pass and terminal completion arrives.
- Cancellation, expiry, source failure, overflow, or truncation omits completion and
  destroys provisional browser state.
- The runtime never falls back from incremental Arrow retrieval to `fetchall()` or full
  row dictionaries.

## Required evidence

- exact two-tool MCP capability and schema tests;
- text/structured parity and malformed/unknown-call tests;
- pending through terminal lifecycle tests with no result-derived fields;
- canaries in cells, column names, SQL, and internal exceptions absent from MCP and
  process output;
- viewer list/lookup behavior and complete-only stream access;
- cancellation, expiry, source failure, and final-batch overflow tests;
- local launcher and development server loopback configuration;
- no browser result storage, external readers, or unbounded main-thread copy; and
- a real MCP Streamable HTTP round trip.
