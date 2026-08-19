# Security

Snowglobe is currently a test-environment MVP. **Do not connect it to a production
Snowflake account, use production credentials, process sensitive data, or use it for
routine analyst work.** One dedicated non-production test credential may be used only
under the constrained exception below.

Snowglobe is designed for one analyst on one machine. The supported service entry
point binds MCP and the local viewer backend to `127.0.0.1`; there is no viewer login,
account system, tenant model, or sharing feature.

## Security property

Snowglobe creates no result-bearing MCP channel. Its MCP surface may return an opaque
request ID, fixed submission reason, and coarse lifecycle state. It must not return
rows, schema, names, counts, sizes, timings, Snowflake identifiers, database errors,
result locations, or result-derived artifacts. Admitted result bytes travel through
the local viewer backend into the browser worker.

Loopback binding reduces accidental remote exposure, but it is not authentication or
same-host isolation. Software running as the analyst—including a powerful coding-agent
host—may be able to access local HTTP endpoints, the browser, screenshots, process
memory, or displayed values. Snowglobe does not defend against that actor. Do not
describe the viewer as “human-only” when the agent controls the same endpoint.

## Constrained connected-MVP exception

The [constrained Snowflake MVP test runbook](docs/constrained-mvp-runbook.md) is the
only authorized connected use. This exception exists solely to collect Gate 5 release
evidence and applies only while every condition below is true:

- the account is dedicated non-production, or the test role is isolated from all
  production access;
- every accessible object contains only non-sensitive synthetic canary data;
- a dedicated key-authenticated test user has no assigned role beyond the dedicated
  read-only role, and the unavoidable `PUBLIC` role has no relevant object access;
- that role has usage only on the reviewed test warehouse, database, and schema and
  select only on explicitly approved test views;
- a small dedicated warehouse is governed by an active administrator-owned resource
  monitor;
- an administrator independently verifies grants, objects, query history, warehouse
  usage, cancellation, and termination throughout the test;
- the local profile and key satisfy Snowglobe's ownership and permission checks,
  remain outside version control and agent-visible artifacts, and are removed or
  revoked after the campaign; and
- Snowglobe is launched exactly as documented, binds only to `127.0.0.1`, and retains
  result bytes only in the local viewer path.

The exception permits only the documented value-free preflight connection and the
documented connected test matrix. It does not permit production or sensitive data,
broader grants, shared credentials, remote exposure, export, screenshots or retained
results, ad hoc queries outside the allowlist, or continued use after a stopping
condition fails. Stop the test immediately if the observed role, warehouse, database,
views, grants, resource monitor, listener addresses, or output channels differ from
the reviewed configuration.

## Reporting a vulnerability

Do not include credentials, query results, personal data, or other sensitive values in
an issue, transcript, screenshot, fixture, or log. Until a private reporting channel
is documented, contact the project owner privately before sharing details.

## Security-sensitive changes

Threat-model and canary review is required for changes to:

- MCP capabilities, schemas, results, transport, status, or errors;
- local network binding, CORS, proxying, or deployment shape;
- SQL parsing, policy, rewriting, roles, warehouses, or query execution;
- Snowflake credentials, query tags, identifiers, or result retrieval;
- broker lifecycle, cancellation, expiry, or local persistence;
- Arrow admission, streaming, framing, logs, traces, or telemetry; or
- browser caching, persistence, external access, rendering, export, or worker lifecycle.

MCP changes must verify exact capabilities and closed schemas, equivalent text and
structured content, malformed and unknown calls, and canary absence. Keep the explicit
low-level handlers; do not replace them with high-level decorators or a third-party
Snowflake MCP without a superseding architecture decision.

See [PLAN.md](PLAN.md), the [connected-MVP runbook](docs/constrained-mvp-runbook.md),
the [threat model](docs/threat-model.md), and
[ADR 0008](docs/decisions/0008-single-analyst-loopback-runtime.md).
