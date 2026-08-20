# Architecture decisions

Snowglobe records consequential technical and security decisions as architecture decision records (ADRs). An accepted ADR describes the current direction; changing it requires a later ADR that names the superseded decision.

| ADR | Status | Decision |
|---|---|---|
| [0001](0001-foundation-stack.md) | Superseded in part by [0008](0008-single-analyst-loopback-runtime.md) and [0012](0012-svelte-viewer.md) | Foundation stack and service boundaries |
| [0002](0002-low-level-mcp.md) | Accepted | Snowglobe owns the low-level MCP surface |
| [0003](0003-snowflake-configuration-names.md) | Superseded by [0016](0016-separate-snowflake-and-snowglobe-configuration.md) | Use Snowflake connector names in `connections.toml` |
| [0004](0004-synthetic-identities-and-broker.md) | Superseded by [0008](0008-single-analyst-loopback-runtime.md) | Separate synthetic audiences and an ownership-enforcing in-process broker |
| [0005](0005-result-stream-framing.md) | Superseded in part by [0008](0008-single-analyst-loopback-runtime.md) and [0017](0017-minimal-model-context-boundary.md) | Failure-atomic Arrow stream framing |
| [0006](0006-incremental-arrow-admission.md) | Superseded in part by [0017](0017-minimal-model-context-boundary.md) | Incrementally validate and serialize actual Arrow record batches |
| [0007](0007-assurance-levels-and-viewer-launch.md) | Superseded in part by [0008](0008-single-analyst-loopback-runtime.md) and [0017](0017-minimal-model-context-boundary.md) | Separate the base product boundary from optional endpoint certification; use a fixed standalone viewer |
| [0008](0008-single-analyst-loopback-runtime.md) | Accepted; security boundary clarified by [0017](0017-minimal-model-context-boundary.md) | Single-analyst loopback runtime with result-free lifecycle polling |
| [0009](0009-constrained-snowflake-mvp-budgets.md) | Accepted | Fixed connection, execution, concurrency, and result budgets for the constrained Snowflake MVP |
| [0010](0010-minimum-snowflake-select-policy.md) | Superseded by [0017](0017-minimal-model-context-boundary.md) | Recursive Snowflake SELECT AST allowlist with approved views, no functions, and a server-owned overflow cap |
| [0011](0011-bounded-snowflake-execution.md) | Superseded in part by [0017](0017-minimal-model-context-boundary.md) | Bounded Snowflake execution and result retention |
| [0012](0012-svelte-viewer.md) | Accepted | Use plain Svelte for the local viewer UI |
| [0013](0013-result-free-cli-adapter.md) | Accepted | Expose the closed control plane to shell-only agents through a CLI client of the local MCP service |
| [0014](0014-pi-extension-package.md) | Accepted; workflow skill superseded by [0017](0017-minimal-model-context-boundary.md) | Package two native Pi tools over the result-free CLI |
| [0015](0015-native-windows-credential-files.md) | Superseded by [0017](0017-minimal-model-context-boundary.md) | Enforce native Windows handle and ACL checks for credential files |
| [0016](0016-separate-snowflake-and-snowglobe-configuration.md) | Accepted; file checks superseded by [0017](0017-minimal-model-context-boundary.md) | Separate native Snowflake connections from Snowglobe query policy |
| [0017](0017-minimal-model-context-boundary.md) | Accepted | Keep only the model-facing result boundary and ordinary correctness controls |
