# Single-analyst local threat model

**Status:** Pre-connected MVP boundary assurance complete
**Last updated:** August 19, 2026

## Scope and claim

One analyst runs Snowglobe and a coding agent on one machine. The analyst's configured
Snowflake identity determines warehouse access. The coding agent supplies SQL through
MCP, the result-free CLI, or the native Pi tools layered over that CLI; the analyst
reviews completed results in the local viewer.

The claim is narrow: Snowglobe's MCP, CLI, and Pi tool output contain only the closed
submission and lifecycle contracts in `PLAN.md`. Query-result bytes and rich metadata
do not travel through these adapters. The local viewer backend is a separate
application path. Enabling the MCP does not grant an agent access to that path.

## Components and allowed data

| Component | Data allowed | Main controls |
|---|---|---|
| Coding agent and MCP/CLI/Pi adapter | Submitted SQL, TTL, opaque request ID, fixed reason, coarse lifecycle | Closed schemas, sanitized exceptions, independent Pi validation, no result reader |
| Local Snowglobe runtime | Query input, policy decision, private execution handle, opaque ID, lifecycle, expiry | One loopback process, value-free logs, request-scoped cleanup |
| Snowflake | Governed SQL and configured credentials | Explicit connector arguments, read-only role, approved views, independent limits |
| Local viewer backend | Request lifecycle and admitted Arrow result | Loopback binding, no-store, stream only complete requests |
| Browser worker | Provisional Arrow and in-memory DuckDB-Wasm table | Failure-atomic publication, memory limits, termination on failure |
| Browser main thread | Request list and bounded viewport/aggregate responses | Escaped rendering, no persistence/telemetry, bounded copies |

## Trust boundary

```text
┌────────────────────── analyst's local security context ──────────────────────┐
│ coding agent ──MCP / CLI / Pi──▶ local runtime ──configured ID──▶ Snowflake  │
│                                  │                                           │
│                                  ├── process-local request broker            │
│                                  │                                           │
│ browser ◀──Arrow── local viewer backend                                      │
└──────────────────────────────────────────────────────────────────────────────┘
```

The local operating-system user boundary is trusted. Browser, screenshot, shell, and
direct HTTP access are separate agent capabilities controlled by the agent host, not
capabilities granted by Snowglobe's MCP. Loopback prevents ordinary remote clients from
connecting; it does not distinguish the browser from another local process.

## Primary threats and controls

| Threat | Control |
|---|---|
| Result values or errors leak through MCP, CLI, or Pi | Closed result schemas; lifecycle-only polling; bounded/discarded process output; independent Pi receipt validation; final exception sanitization; canary scans |
| Service is exposed to the network | Supported launcher and Vite bind to `127.0.0.1`; documentation forbids `0.0.0.0` |
| SQL mutates data or escapes approved objects | One parsed read query; approved views; fixed read-only role/warehouse |
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
- exact CLI receipt output, stdin submission, and sanitized failure tests;
- exact Pi tool registration and schemas, bounded subprocess behavior, independent
  receipt validation, and sanitized failure tests;
- pending through terminal lifecycle tests with no result-derived fields;
- canaries in cells, column names, SQL, and internal exceptions absent from MCP and
  process output;
- viewer list/lookup behavior and complete-only stream access;
- cancellation, expiry, source failure, and final-batch overflow tests;
- local launcher and development server loopback configuration;
- a real MCP Streamable HTTP round trip, including a CLI client call.
