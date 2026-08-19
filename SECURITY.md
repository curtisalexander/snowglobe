# Security

Snowglobe is currently an architecture and proof-of-concept project. **Do not connect it to production Snowflake accounts, use real credentials, or process sensitive data.**

The base security property is that Snowglobe creates no model-facing result channel. Its MCP surface emits only a schema-closed, result-independent receipt, while result bytes are available only through a separately human-authenticated and owner-authorized Result API. This property depends on independently authenticated control and data planes, least-privileged Snowflake access, strict result admission, and browser controls. Splitting the implementation into two model-facing MCP servers would not provide this separation because both return through the agent host.

This base property does not claim that an authorized human, browser, extension, operating system, endpoint, or agent host cannot capture or redisclose displayed data. A deployment may make a stronger model-context exclusion claim only after testing and naming the exact agent host, browser, endpoint configuration, and versions. See [ADR 0007](docs/decisions/0007-assurance-levels-and-viewer-launch.md).

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
- model payload assembly, screenshots, accessibility extraction, or agent-host versions when a deployment makes the stronger certified claim; and
- deployment topology or network policy.

The MCP boundary uses explicit low-level handlers. Any MCP change must test the exact advertised capabilities and schemas, text and structured result channels, malformed and unknown calls, and canary absence. Do not replace this boundary with high-level decorators or a third-party MCP server without a superseding architecture decision and security review.

See [PLAN.md](PLAN.md) for the required boundary and authorization test suites.
