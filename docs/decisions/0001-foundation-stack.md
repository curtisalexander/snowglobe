# ADR 0001: Foundation stack and service boundaries

- **Status:** Accepted for the synthetic proof
- **Date:** August 18, 2026

## Context

Snowglobe needs a model-facing MCP control plane, a separately authenticated Arrow data plane, and a browser viewer whose analytical copy stays in memory. The initial scaffold must make those boundaries visible without implementing an unsafe partial result path.

## Decision

### Backend

- Use Python 3.12+, `uv`, pytest, Ruff, and ty.
- Use the official MCP Python SDK v2 and Streamable HTTP. Run its returned Starlette application directly rather than nesting it under an unnecessary framework.
- Use a separately deployable Starlette Result API. Control- and data-plane processes may share versioned internal packages, but do not share routes, authentication audiences, or public response contracts.
- Use SQLGlot with explicit `read="snowflake"` and `write="snowflake"` dialects as the candidate AST parser and rewriter. It is a parser, not a security policy: Snowglobe must still reject unsupported nodes, allowlist resolved objects/functions, test dialect round trips, and rely on a least-privileged Snowflake role as an independent backstop.
- Use the official Snowflake Python connector, PyArrow, and `cryptography`. Keep Snowflake/PyArrow dependencies in an optional integration extra until the synthetic proof needs them. Do not require the connector's broad `pandas` extra unless an Arrow spike proves it necessary.

### Viewer

- Use React, TypeScript, Vite, Apache Arrow JS, and DuckDB-Wasm.
- Place DuckDB-Wasm under a dedicated application Web Worker. The main thread receives only bounded viewport or chart responses in later milestones.
- Start with the simplest accessible, virtualized table that satisfies the viewport contract. Prototype Mosaic/vgplot for coordinated aggregate charts and compare a dedicated grid only after representative Arrow and memory benchmarks. Avoid committing both stacks before the spike.
- Use npm workspaces because the project currently has one JavaScript package; add a more complex workspace tool only when it removes actual complexity.

### Broker and transport

- Use Streamable HTTP for MCP. Do not use the superseded SSE transport or an MCP App for the MVP.
- Define a broker interface during the synthetic milestone. Begin with an in-process test broker only for boundary tests; select a production store after persisted-result, expiry, multi-process ownership, and deployment topology are known. An in-memory broker is not a production default.
- Reject all query submissions in the scaffold. Do not return an accepted receipt until a request is durably associated with an authenticated human and a governed execution path.

## Rationale

The official MCP SDK v2 has first-class Streamable HTTP and Starlette support, including transport host/origin protections. Starlette is enough for both thin HTTP boundaries, so adding FastAPI would add a framework without reducing complexity. SQLGlot has an actively maintained Snowflake dialect, typed AST traversal, transformation, and Snowflake generation, while its documented normalization and dialect evolution make an adversarial corpus and version pin essential.

DuckDB-Wasm already uses a worker internally, accepts Arrow IPC, and is supported by Vite's explicit worker/Wasm URL pattern. An outer application worker gives Snowglobe one lifecycle owner that can terminate the database on logout, expiry, or stream failure. Mosaic is a strong fit for DuckDB-backed linked views, but a polished table may favor a specialized virtual grid; measurement should decide that tradeoff.

## Deferred deployment decisions

These require the target environment and do not block the synthetic proof:

- enterprise OIDC provider and token claims;
- certified coding-agent host and version;
- approved Snowflake databases, schemas, secure views, functions, and classifications;
- shared service identity versus delegated Snowflake user identity;
- result broker/storage topology and production retention policy;
- representative endpoint memory tiers and browser fleet; and
- audit, incident-response, and regulatory controls.

## Consequences

- The repository contains real, buildable control-plane, data-plane, and viewer shells but no result-bearing endpoint.
- MCP and Result API can be deployed and authenticated independently.
- SQLGlot upgrades are security-sensitive and require corpus/round-trip tests.
- The first implementation iteration should build the synthetic broker and identity seam before Snowflake execution.

## Sources reviewed

- [MCP Python SDK v2](https://github.com/modelcontextprotocol/python-sdk)
- [MCP SDK ASGI guidance](https://py.sdk.modelcontextprotocol.io/run/asgi/)
- [SQLGlot documentation](https://sqlglot.com/)
- [DuckDB-Wasm package guidance](https://www.npmjs.com/package/@duckdb/duckdb-wasm)
- [Mosaic repository and package map](https://github.com/uwdata/mosaic)
- [Querido reuse audit](../querido-reference.md)
