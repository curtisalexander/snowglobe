# ADR 0007: Separate the product boundary from endpoint certification

- **Status:** Accepted
- **Date:** August 19, 2026

## Context

Snowglobe's core product goal is practical: let an agent submit governed SQL while
query results remain available to the human in a DuckDB-Wasm viewer rather than in
model context. Earlier planning coupled that goal to the stronger claim that canaries
are absent from every host-managed channel for exact agent-host and browser versions.
That stronger claim is useful, but it depends on software and endpoint capabilities
outside Snowglobe's control and would make host certification a prerequisite for
building the product.

Using two model-facing MCP servers does not solve this problem. Normal MCP tool results
from either server pass through the host and may be supplied to the model, transcript,
or host telemetry. MCP Apps similarly send tool results through the host; iframe
sandboxing protects the host from app code but does not prove that rendered data is
excluded from model-visible captures.

## Decision

Snowglobe distinguishes two assurance levels.

### Base product guarantee

Snowglobe creates no model-facing result channel:

- its agent-facing MCP surface emits only a schema-closed, result-independent receipt;
- rows, values, schema, counts, sizes, existence, completion state, database errors,
  Snowflake identifiers, result locations, and result-derived artifacts do not cross
  Snowglobe-owned agent-facing interfaces;
- result bytes are released only through a separately human-authenticated,
  owner-authorized Result API; and
- the Result API does not accept the agent or MCP service identity as a viewer identity.

This is a claim about Snowglobe-owned interfaces, not a claim that an authorized human,
browser, operating system, extension, endpoint, or agent host can never capture or
redisclose displayed data. The implementation should avoid deliberate result-dependent
timing signals, but it does not claim formal timing non-interference.

### Certified deployment guarantee

A deployment may additionally claim that displayed canaries do not enter model context
for a named agent host, browser, endpoint configuration, and version set. That claim
requires end-to-end capture tests for model payloads, host history, browser automation,
screenshots, accessibility extraction, and other host-specific paths. Host upgrades
invalidate that evidence until retested.

Certification is optional for the base product and required only when making this
stronger deployment claim. Unknown hosts are outside the certified claim unless the
deployment has a real attestation mechanism that can make them fail closed.

### Viewer launch and service shape

- Keep one model-facing query MCP. A second MCP does not add information-flow isolation
  and is not required merely to launch the viewer.
- Keep the viewer as a standalone web application that calls the Result API directly.
- Give the viewer one deployment-fixed URL with no request ID, result token, or other
  result-specific state in the URL.
- Initially expose that URL through static documentation, a bookmark, or host
  configuration. A later host-specific “Open Snowglobe” action may open the same fixed
  URL, but it remains a result-blind usability adapter rather than a security boundary.
- Do not use an MCP App for result delivery unless a future host supplies and proves an
  app-only data path outside model messages and host captures.

Logical separation of MCP and Result API authentication and authorization is mandatory.
Separate processes or network deployments remain a deployment choice: development may
run them together, while a production environment may isolate the data plane from agent
networks when required.

## Controls retained for other reasons

Incremental Arrow admission, explicit row/column/cell/byte budgets, failure-atomic stream
framing, provisional DuckDB publication, worker ownership, bounded main-thread copies,
and no-persistence defaults remain. They protect result integrity, resource usage, and
data lifecycle even though they are not evidence that a host cannot capture rendered
data.

SQL parsing, object/function policy, server-owned roles and warehouses, timeouts, and a
least-privileged Snowflake role also remain mandatory before sensitive connectivity.
They limit mutation, exfiltration, cost, and availability risk independently of the MCP
information boundary.

## Consequences

- The existing control-plane, Result API, Arrow, and worker architecture remains valid;
  no second result-bearing MCP is added.
- The synthetic vertical slice and useful viewer can be completed without first
  certifying every possible agent host.
- Documentation and tests must state which assurance level they support.
- Snowglobe can make a precise base claim from code and interface tests without making
  an unprovable statement about software outside its boundary.
- Deployments that require end-to-end model exclusion still carry the cost of managed
  endpoint isolation and recurring host certification.

## Sources reviewed

- [MCP tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [MCP Apps overview](https://modelcontextprotocol.io/extensions/apps/overview)
