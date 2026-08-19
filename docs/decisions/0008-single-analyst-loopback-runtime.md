# ADR 0008: Single-analyst loopback runtime

- **Status:** Accepted
- **Date:** August 19, 2026
- **Supersedes:** ADR 0004; the identity, authentication, deployment, and status-disclosure portions of ADRs 0001, 0005, and 0007

## Context

Snowglobe is an individual analyst tool, not a hosted multi-user service. The analyst
already has Snowflake access, asks a coding agent to draft and submit SQL, and reviews
the resulting dataset in a local application. The earlier design introduced enterprise
OIDC, separate agent and viewer identities, request ownership, and independently
authenticated services. Those controls add substantial complexity without serving this
use case.

The analyst needs an asynchronous workflow: submission returns an opaque request ID,
the agent may poll a value-free lifecycle state, and the local viewer may find and open
that same request ID. Result bytes must still never be returned through MCP.

## Decision

- Support one analyst in one local Snowglobe runtime. Do not add viewer accounts,
  OIDC, audiences, tenants, owner fields, sharing, or cross-user authorization.
- Bind the supported local service entry point and Vite development server to
  `127.0.0.1`. Do not expose the viewer backend or MCP on a LAN or public interface.
- Run MCP and the viewer backend in one process with one process-local broker. The
  in-memory implementation is a development seam; restart durability requires a later
  local persistence decision, not a multi-user identity system.
- `submit_read_query` returns the existing closed receipt. On acceptance,
  `request_id` means only that policy admission and asynchronous execution startup
  were established. The current scaffold remains fail-closed until that path exists.
- Add `get_query_status(request_id)`. Its closed response contains exactly the opaque
  request ID and one lifecycle state: `pending`, `complete`, `failed`, `cancelled`,
  `expired`, `not_found`, or `service_unavailable`.
- Lifecycle state is explicitly permitted through MCP. Rows, schema, column names,
  counts, sizes, timing, Snowflake identifiers, query text, driver errors, result
  locations, and all other result-derived information remain prohibited.
- The local viewer backend lists recent requests, looks up an opaque request ID, and
  streams only complete, admitted Arrow results. The browser holds the analytical copy
  in in-memory DuckDB-Wasm and keeps main-thread responses bounded.
- Keep short expiry, cancellation, admission limits, failure-atomic framing,
  no-store headers, no browser persistence, and value-free logs. These protect data
  lifecycle and resources; they are not multi-user authorization controls.

## Security boundary

Loopback binding limits accidental network exposure but is not authentication. A local
process with the analyst's privileges—including a coding-agent host with arbitrary
HTTP, browser, shell, or process access—may be able to call the viewer backend or
capture rendered data. Snowglobe therefore guarantees that its MCP contract does not
return result bytes or rich result metadata; it does not claim adversarial isolation
from other same-host processes.

Analysts who require that stronger isolation must run the viewer on an endpoint the
agent cannot access. That is outside the individual local product defined here and must
not be simulated by reintroducing incomplete authentication machinery.

## Consequences

- The analyst can correlate MCP submission, polling, and local review with one opaque
  request ID.
- There is no login or viewer session in the local application.
- MCP and viewer routes must share one runtime while the broker is process-local;
  launching them as separate Uvicorn processes is unsupported.
- Request IDs are correlators, not secrets. They should remain opaque to avoid exposing
  Snowflake identifiers or query content.
- Hosted, shared, remote, and multi-tenant deployments are non-goals. Supporting one
  later requires a new threat model and superseding ADR.
