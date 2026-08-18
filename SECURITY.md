# Security

Snowglobe is currently an architecture and proof-of-concept project. **Do not connect it to production Snowflake accounts, use real credentials, or process sensitive data.**

The intended security property is not provided by MCP alone. It depends on independently authenticated control and data planes, least-privileged Snowflake access, strict result admission, browser controls, and certification of the exact agent host and deployment.

## Reporting a vulnerability

Do not include credentials, query results, personal data, or other sensitive values in an issue, transcript, screenshot, test fixture, or log. Until a private reporting channel is documented, contact the project owner privately before sharing vulnerability details.

## Security-sensitive changes

Changes involving any of the following require threat-model review and end-to-end canary testing:

- MCP response contracts or transport;
- authentication, authorization, identity, or request ownership;
- SQL parsing, validation, rewriting, or object/function policy;
- Snowflake roles, warehouses, credentials, query tags, or result retrieval;
- Arrow streaming, limits, logging, errors, tracing, or telemetry;
- DuckDB-Wasm storage, extensions, external access, memory, or worker lifecycle;
- browser caching, persistence, CSP, rendering, clipboard, export, or sharing;
- agent-host versions, model payload assembly, screenshots, or accessibility extraction; and
- deployment topology or network policy.

See [PLAN.md](PLAN.md) for the required boundary and authorization test suites.
