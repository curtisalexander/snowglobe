# ADR 0018: Apply the minimal boundary at model-facing adapters

- **Status:** Accepted
- **Date:** August 21, 2026
- **Builds on:** [ADR 0017](0017-minimal-model-context-boundary.md)

## Context

ADR 0017 narrowed Snowglobe's security claim to the output of MCP and its result-free
CLI and Pi adapters. A repository review found remaining controls and documentation
that still treated local diagnostics, every read-query function, browser inspection,
and test-only application modes as parts of that boundary. The same review found an
unbounded request history and one Pi error path that could bypass its closed receipt.

## Decision

- Keep exact, independently validated MCP, CLI, and Pi receipts. Catch every Pi runner
  failure before Pi can turn it into a model-visible tool error.
- Construct MCP only around an explicit `ControlPlane`. Do not create a second global
  runtime, broker, server, or standalone app when the MCP module is imported.
- Require Arrow limits when constructing the viewer API; the supported composed
  runtime always has them, so a limit-free test mode has no product role.
- Keep `Cache-Control: no-store` on viewer responses because automatic persistence is
  unwanted. Remove the generic `X-Content-Type-Options` header because it does not
  contribute to the model-output boundary or the typed result-stream protocol.
- Send only a selected request ID into the application worker. The worker fetches,
  validates, and ingests the result stream; only the worker's bounded viewport data
  returns to the main thread.
- Report useful configuration, key-loading, preflight, and startup diagnostics through
  local operator commands. Those commands are not model-facing query adapters.
- Continue suppressing the Snowflake connector logger because its debug and exceptional
  paths can emit SQL, signed result URLs, response structures, and raw Arrow payloads.
  This is a direct result-byte lifecycle control, not general error secrecy.
- Permit structurally local table functions: `GENERATOR` creates rows and `FLATTEN`
  expands an expression or approved relation. Continue rejecting `RESULT_SCAN`, stage
  directory access, custom table functions, and unknown relation-source shapes because
  they can read outside configured views. Scalar functions remain unrestricted.
- Retain at most 100 active and recent broker records. Evict the oldest failed,
  cancelled, or expired record when needed; never evict an unexpired result or pending
  request to admit new work.
- Test result-canary absence at MCP, CLI, and Pi output boundaries. Browser inspection,
  screenshots, URLs, and ordinary host capabilities are not context-isolation evidence.

## Consequences

- The supported runtime has one explicit dependency graph and fewer test-only states.
- Raw result transport no longer passes through main-thread application code.
- Local setup failures are actionable without widening model-facing receipts.
- Useful local row generation and expansion no longer require a recursive function
  sandbox, while configured-view enforcement still covers alternate data sources.
- Request listing and broker metadata are bounded for a long-running local process.
- Connected validation can use normal browser tools with non-sensitive test data and
  focus its context-exclusion evidence on the actual model-facing adapters.
