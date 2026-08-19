# Snowglobe

<p align="center">
  <img src="assets/snowglobe-logo.webp" alt="A duck, snowflake, and streams of data contained inside a snow globe" width="420">
</p>

**Governed Snowflake results for humans, without putting result data into an AI agent's context.**

Snowglobe is a proposed MCP server and single-page web application for a dual-channel query workflow:

- an AI agent submits governed, read-only Snowflake queries through MCP and receives only an opaque receipt;
- a separately authenticated human opens one fixed, deterministic web viewer;
- Apache Arrow carries bounded results directly from the Result API to the browser; and
- DuckDB-Wasm powers local filtering, sorting, aggregation, and visualization without sending rows back through MCP or the model.

```text
                         CONTROL PLANE — no result data
┌──────────────┐     ┌─────────────┐     ┌───────────┐
│ Agent + LLM  │────▶│ MCP gateway │────▶│ Snowflake │
│              │◀────│             │     │           │
└──────────────┘     └──────┬──────┘     └─────┬─────┘
     opaque receipt         │                  │
                            ▼                  │
                     ┌────────────┐            │
                     │ Result API │◀───────────┘
                     └─────┬──────┘
                           │ authenticated Arrow stream
                  DATA PLANE — no agent transit
                           ▼
                 ┌───────────────────┐
                 │ Human-only SPA    │
                 │ + DuckDB-Wasm     │
                 └───────────────────┘
```

## Status

Snowglobe is building its **synthetic boundary proof**. It is not ready for real credentials or sensitive data. Its MCP surface uses explicit low-level handlers owned by Snowglobe; the official SDK supplies only protocol and Streamable HTTP transport machinery.

A test-only in-process broker models request ownership, separate agent/viewer audiences, expiry, cancellation, and possession-resistant access. The Result API has injected, owner-authorized list/open/cancel/stream seams, incrementally admits actual Arrow record batches, and uses failure-atomic binary framing. The browser worker parses that framing incrementally, inserts Arrow into a provisional in-memory DuckDB table with backpressure, and publishes only after completion and clean stream EOF. The default authenticator denies all result access, admission limits must be explicitly configured, no real token adapter connects the browser yet, and the broker is not a production result store. The checked-in MCP tool therefore still rejects every query. The components are implemented but not yet connected into a complete user journey.

- [Implementation plan](PLAN.md)
- [Documentation index](docs/README.md)
- [Synthetic proof threat model](docs/threat-model.md)
- [Snowflake configuration](docs/configuration.md)
- [Querido reuse audit](docs/querido-reference.md)
- [Architecture decisions](docs/decisions/README.md)
- [Security policy](SECURITY.md)

The first milestone is a synthetic-data proof that unique result canaries are visible in the viewer but absent from Snowglobe-owned agent-facing interfaces, logs, traces, URLs, errors, and browser persistence.

## Core principles

1. **MCP is the control plane, not the data plane.** Rows, schemas, counts, completion, database errors, and result-bearing URLs do not appear in the MCP response.
2. **Authorization, not URL secrecy, protects results.** Request IDs are opaque correlators, never bearer credentials.
3. **The browser is not the admission controller.** Server-side policy bounds query cost, rows, bytes, columns, cells, and estimated memory before release.
4. **One browser analytical copy.** DuckDB-Wasm is the source of truth; the UI reads bounded Arrow windows instead of materializing the dataset as JavaScript row objects.
5. **Claims match the boundary.** The base guarantee covers Snowglobe-owned interfaces. A stronger claim about actual model context requires separate host/browser/endpoint certification.

## Why not two MCPs?

Two model-facing MCP servers are still connected to the same agent host. A result returned by either server may enter the model request, transcript, preview, or host telemetry. MCP Apps also route tool results through the host; iframe sandboxing protects the host from app code but does not create a human-only result channel.

Snowglobe therefore uses one result-blind query MCP plus a separately authenticated Result API and standalone viewer. Opening the viewer is a usability action, not a second data protocol: the human uses one deployment-fixed application URL from a bookmark, static host configuration, or a later host-specific “Open Snowglobe” action. The URL contains no request ID or result token, and viewer authorization—not possession of the URL—controls access.

This architecture provides a maintainable base guarantee: Snowglobe creates no model-facing result channel. It does not claim that an authorized human, browser, extension, operating system, endpoint, or agent host can never capture displayed data. Deployments that need that stronger claim must isolate and certify those endpoint paths explicitly.

## Snowflake connection

The server will use an operator-owned `connections.toml` profile with Snowflake key-pair authentication. Start from [`connections.example.toml`](connections.example.toml); never commit the real file or private key. Snowglobe has adapted Querido's narrow configuration and private-key patterns; connection lifecycle, request-scoped cursors, and incremental Arrow retrieval remain planned Snowglobe-owned work.

## Development

Requirements:

- [`uv`](https://docs.astral.sh/uv/) and a Python 3.12 toolchain;
- Node.js 22.12 or newer and npm.

Fresh Amp orbs run `.agents/setup`, which installs `uv`, Python 3.12, Node.js 24, and the locked Python and npm dependencies.

```bash
uv sync
npm install

uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest

npm run lint
npm run typecheck
npm test
npm run build
```

Run the deliberately closed backend apps locally:

```bash
uv run uvicorn snowglobe.mcp_gateway:app --port 8000
uv run uvicorn snowglobe.result_api:app --port 8001
npm run dev
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`. The Result API exposes a value-free `/healthz`; its result routes fail closed under the default deny-all authenticator. Synthetic tests inject verified viewer claims, but no public token adapter or real result source is configured.

## Repository layout

```text
apps/viewer/          React/Vite SPA and DuckDB-Wasm worker
src/snowglobe/        MCP, Result API, contracts, and test-only broker
tests/                backend contract, configuration, key, and API tests
docs/decisions/       architecture decision records
docs/                 current docs plus retained source design material
assets/               generated project artwork
.agents/              Amp orb setup and resume hooks
AGENTS.md              durable implementation and verification guardrails
```

## License

[MIT](LICENSE) © 2026 Curtis Alexander
