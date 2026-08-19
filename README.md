# Snowglobe

<p align="center">
  <img src="assets/snowglobe-logo.webp" alt="A duck, snowflake, and streams of data contained inside a snow globe" width="420">
</p>

**A local Snowflake query MCP and result viewer for one analyst.**

Snowglobe lets a coding agent submit governed read-only SQL without putting the query
result into the MCP response. Submission will run asynchronously and return an opaque
request ID. The agent may poll that ID for a small lifecycle state, while the analyst
uses the same ID in a local viewer to inspect the result.

```text
                         MCP — control only
┌──────────────┐     ┌────────────────────────┐     ┌───────────┐
│ Analyst's    │────▶│ local Snowglobe runtime│────▶│ Snowflake │
│ coding agent │◀────│ submit + status        │     │           │
└──────────────┘     └───────────┬────────────┘     └─────┬─────┘
       opaque ID + lifecycle     │                        │
                                 │ shared local broker    │
                                 ▼                        │
                      ┌──────────────────────┐             │
                      │ local viewer backend│◀────────────┘
                      └──────────┬───────────┘
                                 │ admitted Arrow stream
                                 ▼
                      ┌──────────────────────┐
                      │ browser worker      │
                      │ + DuckDB-Wasm       │
                      └──────────────────────┘
```

There are no viewer accounts, enterprise OIDC, tenants, owner claims, or sharing. MCP
and viewer routes run in one process and bind to loopback for individual use.

## Status

Snowglobe is still a synthetic proof and is **not ready for real credentials or
sensitive data**. Implemented pieces include:

- explicit low-level MCP contracts for `submit_read_query` and
  `get_query_status`;
- a single-analyst broker with pending, complete, failed, cancelled, and expired
  lifecycle states;
- local viewer routes to list, find, cancel, and stream a request;
- incremental Arrow admission and failure-atomic framing; and
- in-memory DuckDB-Wasm ingestion with a bounded main-thread viewport.

The submit tool intentionally still returns `SERVICE_UNAVAILABLE`: SQL policy,
Snowflake execution, and atomic asynchronous registration are not connected yet. The
next implementation item is that governed executor path.

- [Implementation plan](PLAN.md)
- [Single-analyst architecture decision](docs/decisions/0008-single-analyst-loopback-runtime.md)
- [Threat model](docs/threat-model.md)
- [Security policy](SECURITY.md)
- [Documentation index](docs/README.md)

## Boundary

MCP may return only:

- an accepted/rejected submission receipt with an opaque request ID and fixed reason;
  or
- an opaque request ID plus `pending`, `complete`, `failed`, `cancelled`, `expired`,
  `not_found`, or `service_unavailable`.

MCP must not return rows, schema, column names, counts, sizes, timing, Snowflake query
IDs, database errors, result URLs, or result-derived artifacts. Result bytes travel
only through the local viewer backend into the browser worker.

Loopback is not authentication or process isolation. A coding agent with arbitrary
same-host HTTP, browser, shell, or process access may be able to call the local viewer
backend or capture rendered data. Snowglobe prevents an automatic result-bearing MCP
channel; it does not claim to defend the analyst's data from other processes running as
that analyst.

## Local development

Requirements are Python 3.12 with `uv`, plus Node.js 22.12 or newer and npm.

```bash
uv sync
npm install

# One loopback process owns MCP, viewer routes, and the in-memory broker.
uv run snowglobe-local

# In another terminal; Vite proxies viewer API calls to the local runtime.
npm run dev
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`. Do not launch the MCP and viewer
backend as separate processes while the broker is in memory, and do not bind either
service to `0.0.0.0`.

Run all checks with:

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
npm run lint
npm run typecheck
npm test
npm run build
```

The future Snowflake executor reads a local `connections.toml` profile. Start from
[`connections.example.toml`](connections.example.toml); never commit the real file or
private key.

## License

[MIT](LICENSE) © 2026 Curtis Alexander
