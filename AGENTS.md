# Snowglobe agent guidance

Snowglobe is a security-sensitive dual-channel system: an AI agent may submit a governed query, but query-result information must reach only a separately authenticated human viewer. Read `PLAN.md`, `SECURITY.md`, and the relevant ADRs in `docs/decisions/` before changing a boundary.

## Non-negotiable boundaries

- MCP is control plane only. Never return rows, values, schema, counts, sizes, completion state, Snowflake identifiers, database errors, result URLs, images, resources, or other result-derived information through MCP.
- The model-facing contract is exactly the allowlisted receipt documented in `PLAN.md`. Keep text and structured MCP content equivalent and schema-closed.
- Use Snowglobe's explicit low-level `mcp.server.Server` handlers. Do not introduce `MCPServer`, `FastMCP`, high-level decorators, MCP resources/prompts, or a third-party Snowflake/Querido MCP server.
- The official MCP SDK owns protocol framing and Streamable HTTP transport only. Snowglobe owns handlers, schemas, validation, capabilities, result construction, and public errors.
- Result bytes travel through the separately authenticated Result API, never through MCP, local files visible to an agent, logs, traces, URLs, or shared metadata.
- Fail closed. Do not add a placeholder path that accepts work before ownership, policy, admission, and failure-atomic publication exist together.

## Snowflake and SQL

- `connections.toml` is operator-owned and server-only. Its exact schema uses `database`, never `db`; unknown fields are rejected. Never commit the real file or a private key.
- Build Snowflake connector arguments from an explicit allowlist. Role, warehouse, database, profile, authenticator, and key path are never tool inputs.
- Use SQLGlot with the Snowflake dialect for parsing/generation, then enforce a Snowglobe-owned recursive AST policy. A parser is not authorization.
- Accept only the documented query subset and use a least-privileged Snowflake role as an independent backstop. Never use regex or first-keyword classification as the policy boundary.
- Arrow retrieval must remain incremental. Do not concatenate complete results, call `to_pylist()`, build full row dictionaries, or fall back to `fetchall()`.

## Browser data handling

- DuckDB-Wasm lives in the dedicated application worker and remains in memory.
- Do not add IndexedDB, OPFS, service-worker result caching, automatic restoration, export, external readers/extensions, or third-party telemetry without a new reviewed decision.
- Main-thread table and chart data must be bounded viewport or aggregate responses, not a second full result copy.

## Documentation and decisions

- Update `PLAN.md` when implementation status or sequencing changes.
- Record consequential architecture/security choices as ADRs and add them to `docs/decisions/README.md`.
- `docs/architecture-proposal.md` and the companion HTML files are retained source material. Do not silently rewrite them to match later decisions; document superseding decisions in ADRs and the plan.
- `docs/querido-reference.md` is a pinned audit of Querido commit `eb6879e80a09acd0a4c090c42801d68f7fc101d9`. Preserve that provenance.

## Verification

Run the relevant focused checks while iterating, then before completion run:

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

For MCP changes, additionally verify exact advertised capabilities and schemas, both result channels, malformed/unknown calls, canary absence, and a real Streamable HTTP client round trip. For documentation changes, verify local Markdown links and final newlines.
