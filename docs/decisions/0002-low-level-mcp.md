# ADR 0002: Snowglobe owns the low-level MCP surface

- **Status:** Accepted
- **Date:** August 18, 2026

## Context

Snowglobe's security claim depends on controlling every model-visible capability, schema, result field, error, and metadata channel. Reusing Snowflake's MCP server or Querido's proposed MCP wrapper would import contracts and behavior that intentionally expose more information than Snowglobe permits. The official MCP Python SDK's high-level decorator API also derives schemas, advertises capability families, validates arguments, and serializes results automatically.

Reimplementing the MCP protocol itself would add security-sensitive work around JSON-RPC framing, initialization, version negotiation, Streamable HTTP, cancellation, and client compatibility without improving Snowglobe's product behavior.

## Decision

Build Snowglobe's MCP server with the official MCP Python SDK's low-level `Server` API:

- Snowglobe implements explicit `tools/list` and `tools/call` handlers.
- Snowglobe handwrites and manually enforces the input and output schemas.
- Snowglobe constructs every `CallToolResult`, including both text and structured content.
- Only the tools capability is registered; resources and prompts are not advertised.
- Unknown tools, invalid arguments, policy rejection, and internal failures cross the boundary only through fixed, non-reflective responses.
- The initial server is stateless and uses the standard MCP Streamable HTTP transport with JSON responses.
- The official SDK is retained only for MCP protocol framing, initialization and version negotiation, transport behavior, and interoperability.

Do not reuse Snowflake's MCP server, Querido's MCP design, or high-level MCP decorators for the model-facing boundary.

## Consequences

- The complete model-facing surface is visible in one low-level module and can be tested byte-for-byte.
- Input JSON Schema is descriptive at the low-level SDK layer, so Snowglobe must validate every argument itself.
- Output schema and result content can drift unless contract tests compare them.
- SDK upgrades remain security-sensitive because protocol and transport behavior can change.
- Snowglobe still benefits from standard MCP clients and does not own a custom protocol fork.

## Required evidence

Tests must verify:

- initialization advertises only the tools capability;
- exactly one tool and its exact closed schemas are listed;
- text and structured receipt representations contain the same allowlisted fields;
- submitted canaries do not appear in results or errors;
- unknown tool names and malformed values are not reflected; and
- the same contract works through a real Streamable HTTP client connection.
