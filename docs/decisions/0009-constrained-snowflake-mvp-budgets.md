# ADR 0009: Constrained Snowflake MVP budgets

- **Status:** Accepted
- **Date:** August 19, 2026
- **Builds on:** [ADR 0008](0008-single-analyst-loopback-runtime.md)

## Context

Snowglobe needs fixed safety budgets before its synthetic executor can be connected to
a non-production Snowflake environment. The initial viewer can inspect at most 50 rows
and 256 KiB, and the process-local broker has no restart durability. Connector-side
timeouts are not hard wall-clock deadlines: an in-flight socket operation may overrun
them, and `fetch_arrow_batches()` has no independent timeout argument. Snowflake
server parameters and a constrained warehouse must therefore remain independent
backstops.

These values are deliberately conservative test-MVP budgets, not production sizing or
representative analyst workload limits.

## Decision

- Admit at most one pending request in the supported runtime.
- Cap request lifetime at five minutes.
- Configure the Snowflake connector with:
  - `login_timeout=30` seconds;
  - `network_timeout=60` seconds; and
  - `socket_timeout=15` seconds.
- Configure these server session parameters:
  - `STATEMENT_TIMEOUT_IN_SECONDS=60`;
  - `STATEMENT_QUEUED_TIMEOUT_IN_SECONDS=15`; and
  - `ABORT_DETACHED_QUERY=TRUE`.
- Admit at most 50 rows, 32 columns, 16 KiB per variable-width cell, 256 KiB of
  serialized Arrow, and 256 KiB of cumulative decoded Arrow.
- Give the browser parser, ingestion queue, and viewport the same 256-KiB result-input
  ceiling. This bounds Snowglobe-controlled result input; it is not a hard browser
  process-RSS limit because DuckDB-Wasm and the browser add overhead.
- Keep the direct Result API factory fail-closed without injected limits. Only the
  supported shared local launcher installs these MVP budgets.
- Provide a preflight command that validates local configuration and key material
  without connecting by default. Its explicit connected mode opens and closes one
  cursor but executes no SQL and emits only fixed pass/fail text.

## Consequences

- Results larger than the one bounded MVP viewport are rejected rather than silently
  truncated. Pagination and larger results remain deferred.
- A second pending query receives the existing value-free service-unavailable path;
  completed synthetic results do not consume execution capacity.
- Server statement and queue deadlines limit work if client cancellation or network
  timers are delayed. `ABORT_DETACHED_QUERY` is an additional async/disconnect
  backstop; synchronous queries are expected to abort on connection loss.
- Arrow retrieval still needs an application-owned wall-clock deadline and cleanup in
  the real executor, because connector execution timers end before later result-chunk
  downloads.
- Raising any result or concurrency budget requires browser-memory evidence and a
  review of Snowflake cost and cancellation behavior.
