# ADR 0017: Minimal model-context boundary

- **Status:** Accepted
- **Date:** August 20, 2026
- **Supersedes:** Security claims and controls in ADRs 0005–0011, 0015, and 0016 that are not part of the model-facing output boundary

## Context

Snowglobe has one security goal: query results must not be returned to the model
through Snowglobe's MCP or its result-free adapters. The analyst must still be able to
open those results in a local browser data viewer.

Earlier work accumulated controls aimed at protecting data from other local accounts,
same-host processes, browser access, broad SQL syntax, ordinary inherited file access,
and internal components that had already admitted data. Those controls do not enforce
the model-facing output boundary and made the local product difficult to understand and
operate.

Browser automation, screenshots, loopback HTTP, accessibility, shell, and process
access are separate agent capabilities. The agent host decides whether to enable them;
enabling Snowglobe's MCP does not enable them. Snowglobe's enforceable guarantee is
that its MCP and result-free adapters do not return query results.

## Decision

- MCP exposes only query submission and coarse lifecycle polling. Its exact closed
  receipts contain no rows, schema, counts, sizes, timing, SQL, database errors,
  Snowflake identifiers, result locations, or result-derived artifacts.
- The CLI and Pi adapters, where used, independently validate those same receipts
  before emitting model-facing output.
- Result bytes travel through separate loopback viewer routes into the browser worker.
  Enabling Snowglobe's MCP does not grant access to those routes. Loopback limits
  accidental remote exposure but is not authentication.
- Configuration and key paths are explicit analyst inputs. Snowglobe uses normal file
  reads and relies on the analyst and operating system for file access policy.
- SQL policy accepts one parsed Snowflake read query, restricts external relations to
  configured views, and applies a server-owned row cap. The configured read-only
  Snowflake role is the mutation and object-access boundary; Snowglobe does not
  maintain a recursive expression or function sandbox.
- Arrow rows, columns, cells, decoded memory, and serialized bytes are admitted once
  before broker publication. Viewer streaming serializes that admitted source with a
  transport byte ceiling; it does not repeat full admission.
- Submission returns after policy admission, pending registration, and successful task
  scheduling. Cursor registration may happen later; the broker cancels a cursor that
  arrives after cancellation or expiry.
- Keep timeouts, cancellation, cleanup, bounded memory, failure-atomic browser
  publication, worker ownership, and no automatic persistence as product correctness
  and data-lifecycle behavior, not as model-isolation claims.
- Remove the unused query `purpose`, unused viewer cancellation route, redundant Pi
  workflow skill, and response headers that do not affect data API behavior. Keep
  `Cache-Control: no-store` and `X-Content-Type-Options: nosniff` on viewer responses.

## Consequences

- The enforceable boundary is small enough to audit directly in the MCP, CLI, and Pi
  contracts and canary tests.
- An agent given a separate capability that can access the viewer may read results. A
  local account that can access configuration or key files can read or modify them.
- Snowflake least-privilege grants are required for read-only operation. SQL functions
  and ordinary read-query expressions are allowed; connector timeouts and result
  limits bound execution and retrieval.
- Browser and broker lifecycle controls remain because partial, stale, or unbounded
  data is a correctness problem even though it is not a model-context boundary.
