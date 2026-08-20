# ADR 0013: Add a result-free CLI adapter over the local MCP service

- **Status:** Accepted
- **Date:** August 19, 2026

## Context

Some coding agents, including Pi, can execute local shell commands but cannot connect
to MCP servers. Snowglobe's submission and lifecycle behavior was previously embedded
in the MCP handler, and its executor and result source live in the server's
process-local broker. A one-shot CLI cannot safely instantiate that runtime itself:
exiting after submission would destroy the background task and make its request and
result unavailable to the viewer.

CLI output read by an agent is model-facing just like an MCP response. Adding a shell
adapter must not create a result, error, metadata, or configuration channel broader
than the existing closed MCP contracts.

## Decision

- Extract submission, fixed failure mapping, lifecycle lookup, and receipt construction
  into a transport-neutral `ControlPlane` with explicit broker and executor
  dependencies.
- Construct the low-level MCP `Server` around a `ControlPlane`; keep MCP schemas,
  argument validation, protocol framing, and text/structured result construction in
  the MCP adapter.
- Add a `snowglobe` CLI with only `submit` and `status` commands. The CLI is a client of
  the already-running fixed loopback MCP endpoint; it never constructs a second
  executor or broker.
- Read submitted SQL from standard input so it is not a Snowglobe process argument.
- Emit exactly one validated `QueryReceipt` or `QueryStatusReceipt` JSON object on
  stdout. Treat transport failures and malformed server responses as fixed,
  result-free service-unavailable receipts. Map malformed command-line input to a
  closed invalid-request or `not_found` receipt without reflection.
- Do not add CLI commands for viewer discovery, cancellation, result streaming,
  configuration, schema, rows, counts, errors, URLs, or other result-derived data.
- Keep the supported daemon, MCP endpoint, viewer routes, executor, and in-memory
  broker in one loopback-only process.

## Consequences

- Pi and other shell-capable agents can use Snowglobe without native MCP support.
- MCP clients and CLI users reach the same runtime and receive the same closed receipt
  models.
- The CLI requires `snowglobe-local` to be running and cannot provide an offline or
  standalone submission mode.
- The MCP Python SDK remains a runtime dependency of the CLI because it owns the
  client-side Streamable HTTP protocol.
- CLI stdout, stderr, exit behavior, transport failures, and canary absence become
  security-sensitive test surfaces.

## Required evidence

Tests must verify that:

- the control plane maps accepted, policy-rejected, unavailable, and lifecycle paths
  to the closed receipt models without result data;
- MCP factory instances use their supplied control plane rather than mutable module
  globals;
- CLI submission reads SQL from stdin and emits only the submission receipt;
- CLI status emits only the lifecycle receipt;
- transport failures and malformed responses fail closed without reflecting private
  input or errors; and
- the existing MCP capability, schema, parity, malformed-call, canary, and real
  Streamable HTTP tests continue to pass.
