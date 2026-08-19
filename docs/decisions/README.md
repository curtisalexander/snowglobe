# Architecture decisions

Snowglobe records consequential technical and security decisions as architecture decision records (ADRs). An accepted ADR describes the current direction; changing it requires a later ADR that names the superseded decision.

| ADR | Status | Decision |
|---|---|---|
| [0001](0001-foundation-stack.md) | Accepted | Foundation stack and service boundaries |
| [0002](0002-low-level-mcp.md) | Accepted | Snowglobe owns the low-level MCP surface |
| [0003](0003-snowflake-configuration-names.md) | Accepted | Use Snowflake connector names in `connections.toml` |
| [0004](0004-synthetic-identities-and-broker.md) | Accepted for synthetic proof | Separate synthetic audiences and an ownership-enforcing in-process broker |
| [0005](0005-result-stream-framing.md) | Accepted for synthetic proof | Owner-authorized Result API and failure-atomic Arrow stream framing |
| [0006](0006-incremental-arrow-admission.md) | Accepted for synthetic proof | Incrementally validate and serialize actual Arrow record batches |
| [0007](0007-assurance-levels-and-viewer-launch.md) | Accepted | Separate the base product boundary from optional endpoint certification; use a fixed standalone viewer |
