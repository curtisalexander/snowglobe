# Security

Snowglobe is currently a proof of concept. **Do not connect it to a production
Snowflake account, use real credentials, or process sensitive data.**

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

See [PLAN.md](PLAN.md), the [threat model](docs/threat-model.md), and
[ADR 0008](docs/decisions/0008-single-analyst-loopback-runtime.md).
