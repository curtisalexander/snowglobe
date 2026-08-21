# ADR 0021: Return governed SQL in submission receipts

- **Status:** Accepted
- **Date:** August 21, 2026
- **Supersedes:** The model-facing SQL exclusion in
  [ADR 0017](0017-minimal-model-context-boundary.md), the Pi SQL-result exclusion in
  [ADR 0014](0014-pi-extension-package.md), and the terminal-only restriction in
  [ADR 0020](0020-print-governed-sql-for-the-operator.md)

## Context

The agent authors the submitted SQL and therefore already has it in model context.
Snowglobe then parses, authorizes, caps, regenerates, and re-authorizes that statement.
The exact governed SQL may differ from the draft and is the useful statement to display
alongside the opaque request ID in a model harness.

The existing submission tool already owns both policy admission and the request receipt.
A separate lookup tool would add another model action and require retaining SQL by
request ID solely for later retrieval.

## Decision

- Add required `governed_sql` to the existing submission receipt.
- For an accepted submission, return the exact non-empty SQL produced by policy
  authorization and scheduled for the connector execution attempt.
- For a rejected submission, return `governed_sql: null`; no SQL was admitted for
  execution.
- Return the same field through MCP text and structured content, the CLI, and Pi. Keep
  independent exact-schema validation at each adapter.
- Keep lifecycle receipts unchanged. Do not add SQL to broker records, viewer routes,
  logs beyond the existing foreground diagnostic, or a new MCP tool.
- Continue excluding rows, result schema, counts, sizes, timing, database errors,
  Snowflake identifiers, result locations, and all other result-derived information
  from model-facing adapters.

## Consequences

- Model harnesses can display the request ID and exact governed SQL in one tool result.
- The submission receipt is intentionally model-visible and may repeat sensitive SQL
  literals that were already present in the model-authored tool call.
- Policy rejection and pre-admission failures do not reflect submitted SQL.
- A later execution failure does not add driver details; status polling still reports
  only `failed`.
- The foreground runtime diagnostic remains useful for operator and service-manager
  troubleshooting, but it is no longer the only interface that displays governed SQL.
