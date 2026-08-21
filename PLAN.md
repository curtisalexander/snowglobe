# Snowglobe plan

**Status:** Ready for connected MVP validation
**Last updated:** August 21, 2026
**Current decision:** [ADR 0019](docs/decisions/0019-relation-centric-sql-authorization.md)

## Product

Snowglobe is a local application for one analyst:

1. an agent submits one Snowflake read query through MCP;
2. MCP returns an opaque request ID and coarse lifecycle states only;
3. Snowglobe executes the query with a fixed read-only profile; and
4. the analyst opens the result in a browser data viewer.

The MCP tools are `submit_read_query(sql, requested_ttl)` and
`get_query_status(request_id)`.

## Security boundary

Model-facing MCP, CLI, and Pi output may contain only:

- submission `status`: `accepted` or `rejected`;
- an opaque `request_id`;
- a fixed submission `reason_code`; and
- lifecycle `status`: `pending`, `complete`, `failed`, `cancelled`, `expired`,
  `not_found`, or `service_unavailable`.

They must not contain rows, values, schema, names, counts, sizes, timing, SQL, database
errors, Snowflake identifiers, result locations, or result-derived artifacts. Text and
structured MCP content must be equivalent and schema-closed.

Result bytes travel through separate loopback viewer routes into the browser worker.
Enabling Snowglobe's MCP does not grant access to those routes. Browser, screenshot,
shell, and direct HTTP access are separate capabilities controlled by the agent host
and outside the MCP contract.

## Architecture that pays for itself

- One loopback process owns MCP, viewer routes, execution, and the in-memory broker.
- The broker retains at most 100 active and recent requests without evicting live
  results to make room.
- A fixed Snowflake profile owns the role, warehouse, database, authenticator, and key.
- SQLGlot accepts one read query, restricts external relations to configured views,
  re-authorizes generated SQL, and applies a server-owned row cap. Unknown relation
  sources fail closed; ordinary query expressions remain available. Snowflake
  read-only grants independently prevent mutation.
- Connection, queue, statement, and socket timeouts bound work and cost.
- Arrow retrieval is incremental and admitted once before publication using row,
  column, cell, serialized-byte, and decoded-memory limits.
- The browser receives a failure-atomic framed Arrow stream and publishes it only after
  the completion frame. DuckDB-Wasm remains worker-local; the main thread receives a
  bounded escaped viewport.
- Cancellation, expiry, resource cleanup, and shutdown handling are correctness
  controls. Viewer responses use `no-store`; browser results are not automatically
  persisted.
- Local configuration and startup commands may report actionable operator diagnostics;
  model-facing MCP, CLI, and Pi failures remain closed receipts.

## Current verification target

Use a dedicated non-production Snowflake identity with a genuinely read-only role and
non-sensitive test data. Verify:

- one allowed query reaches `accepted` → `pending` → `complete` and opens in the
  browser viewer;
- one mutation, one multi-statement input, and one unapproved relation are rejected or
  blocked by the read-only role;
- empty, oversized, timeout, cancellation, expiry, failure, and restart paths remain
  bounded;
- result canaries appear in the viewer stream but never in MCP, CLI, or Pi output; and
- the complete Python and TypeScript checks pass.

## Next product work

- Add useful DuckDB-backed pagination, sorting, filtering, and projection.
- Add one bounded aggregate chart.
- Improve local packaging and startup.
- Add richer operator diagnostics without changing model-facing receipts.

Durable requests, export, sharing, remote hosting, accounts, tenants, and viewer
authentication are not part of the local single-analyst product.
