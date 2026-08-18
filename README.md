# Snowglobe

<p align="center">
  <img src="assets/snowglobe-logo.webp" alt="A duck, snowflake, and streams of data contained inside a snow globe" width="420">
</p>

**Governed Snowflake results for humans, without putting result data into an AI agent's context.**

Snowglobe is a proposed MCP server and single-page web application for a dual-channel query workflow:

- an AI agent submits governed, read-only Snowflake queries through MCP and receives only an opaque receipt;
- a separately authenticated human opens the result in a deterministic web viewer;
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

A test-only in-process broker now models request ownership, separate agent/viewer audiences, expiry, cancellation, and possession-resistant access. It is not connected to either public app, does not authenticate tokens, and is not a production result store. The checked-in MCP tool therefore still rejects every query, and the Result API still exposes no result-bearing route.

- [Implementation plan](PLAN.md)
- [Documentation index](docs/README.md)
- [Synthetic proof threat model](docs/threat-model.md)
- [Snowflake configuration](docs/configuration.md)
- [Querido reuse audit](docs/querido-reference.md)
- [Architecture decisions](docs/decisions/README.md)
- [Security policy](SECURITY.md)

The first milestone is a synthetic-data proof that unique result canaries are visible in the viewer but absent from every agent-visible channel, log, trace, URL, and error.

## Core principles

1. **MCP is the control plane, not the data plane.** Rows, schemas, counts, database errors, and result-bearing URLs do not appear in the MCP response.
2. **Authorization, not URL secrecy, protects results.** Request IDs are opaque correlators, never bearer credentials.
3. **The browser is not the admission controller.** Server-side policy bounds query cost, rows, bytes, columns, cells, and estimated memory before release.
4. **One browser analytical copy.** DuckDB-Wasm is the source of truth; the UI reads bounded Arrow windows instead of materializing the dataset as JavaScript row objects.
5. **Claims are scoped and tested.** “Zero-context results” applies only to certified hosts, server versions, and tested information flows.

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

Run the deliberately closed backend shells locally:

```bash
uv run uvicorn snowglobe.mcp_gateway:app --port 8000
uv run uvicorn snowglobe.result_api:app --port 8001
npm run dev
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`; the Result API currently exposes only a value-free `/healthz`. Do not add a result route until human authentication, ownership authorization, admission, and failure-atomic Arrow streaming are implemented together.

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
