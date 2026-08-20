# Architecture decisions

Snowglobe records consequential technical and security decisions as architecture decision records (ADRs). An accepted ADR describes the current direction; changing it requires a later ADR that names the superseded decision.

| ADR | Status | Decision |
|---|---|---|
| [0001](0001-foundation-stack.md) | Superseded in part by [0008](0008-single-analyst-loopback-runtime.md) and [0012](0012-svelte-viewer.md) | Foundation stack and service boundaries |
| [0002](0002-low-level-mcp.md) | Accepted | Snowglobe owns the low-level MCP surface |
| [0003](0003-snowflake-configuration-names.md) | Superseded by [0016](0016-separate-snowflake-and-snowglobe-configuration.md) | Use Snowflake connector names in `connections.toml` |
| [0004](0004-synthetic-identities-and-broker.md) | Superseded by [0008](0008-single-analyst-loopback-runtime.md) | Separate synthetic audiences and an ownership-enforcing in-process broker |
| [0005](0005-result-stream-framing.md) | Superseded in part by [0008](0008-single-analyst-loopback-runtime.md) | Failure-atomic Arrow stream framing |
| [0006](0006-incremental-arrow-admission.md) | Accepted for synthetic proof | Incrementally validate and serialize actual Arrow record batches |
| [0007](0007-assurance-levels-and-viewer-launch.md) | Superseded in part by [0008](0008-single-analyst-loopback-runtime.md) | Separate the base product boundary from optional endpoint certification; use a fixed standalone viewer |
| [0008](0008-single-analyst-loopback-runtime.md) | Accepted | Single-analyst loopback runtime with result-free lifecycle polling |
| [0009](0009-constrained-snowflake-mvp-budgets.md) | Accepted | Fixed connection, execution, concurrency, and result budgets for the constrained Snowflake MVP |
| [0010](0010-minimum-snowflake-select-policy.md) | Accepted; configuration ownership superseded by [0016](0016-separate-snowflake-and-snowglobe-configuration.md) | Recursive Snowflake SELECT AST allowlist with approved views, no functions, and a server-owned overflow cap |
| [0011](0011-bounded-snowflake-execution.md) | Accepted | Cursor-before-acceptance Snowflake execution with incremental admission and bounded in-memory result retention |
| [0012](0012-svelte-viewer.md) | Accepted | Use plain Svelte for the local viewer UI |
| [0013](0013-result-free-cli-adapter.md) | Accepted | Expose the closed control plane to shell-only agents through a CLI client of the local MCP service |
| [0014](0014-pi-extension-package.md) | Accepted | Package two native Pi tools and a workflow skill over the result-free CLI |
| [0015](0015-native-windows-credential-files.md) | Accepted | Enforce native Windows handle and ACL checks for credential files |
| [0016](0016-separate-snowflake-and-snowglobe-configuration.md) | Accepted | Separate native Snowflake connections from Snowglobe query policy |
