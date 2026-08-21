# ADR 0020: Print governed SQL for the local operator

- **Status:** Accepted
- **Date:** August 21, 2026
- **Builds on:** [ADR 0017](0017-minimal-model-context-boundary.md) and
  [ADR 0019](0019-relation-centric-sql-authorization.md)

## Context

An agent supplies SQL to Snowglobe, then Snowglobe parses, authorizes, caps, regenerates,
and re-authorizes it before execution. The regenerated statement can differ from the
agent's draft and is the useful artifact when an analyst troubleshoots behavior.

Returning that statement through MCP, the result-free CLI, or Pi would violate their
closed model-facing contracts. Retaining it in broker metadata or adding it to viewer
routes would widen more interfaces than the troubleshooting need requires.

## Decision

- Immediately before calling the Snowflake connector's `execute`, print the opaque
  request ID and exact governed SQL to the foreground `snowglobe-local` output.
- Describe the message as an execution attempt: connector execution may still fail.
- Do not add SQL to broker views, MCP, CLI, Pi, or viewer response schemas, and do not
  add a Snowglobe-managed query log.
- Document that terminals and service managers may capture output and that SQL may
  contain sensitive literals.

## Consequences

- The analyst can correlate a request receipt with the exact formatted and capped SQL
  submitted to the connector.
- Rejected SQL prints nothing because it never reaches a connector execution attempt.
- A successful statement is the SQL that ran; for a failed request, the message shows
  the exact statement that Snowglobe attempted.
- The model-facing schemas and the broker's value-free lifecycle metadata remain
  unchanged.
