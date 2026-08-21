# ADR 0019: Commit to relation-centric SQL authorization

- **Status:** Accepted
- **Date:** August 21, 2026
- **Builds on:** [ADR 0017](0017-minimal-model-context-boundary.md) and
  [ADR 0018](0018-minimal-boundary-cleanup.md)

## Context

SQL authorization is useful product behavior and a potential Snowglobe differentiator,
not merely model-context protection. The policy must prevent direct destructive
statements and references to unapproved relations while supporting ordinary analytics.

Trying to recursively allowlist the complete Snowflake expression grammar would create
a permanent edge-case project. Relaxing relation validation, however, would discard the
most valuable and structurally enforceable part of the feature. Review also found that
SQLGlot parses `SELECT ... INTO` as `Select` but generates mutating `CREATE TABLE AS
SELECT` SQL, demonstrating that input-AST validation alone is insufficient.

## Decision

- Go all-in on two invariants: the executed SQL is exactly one query, and every direct
  external relation in that query is a configured fully qualified identity.
- Parse, authorize, and cap submitted SQL; generate Snowflake SQL; then parse and
  authorize the generated SQL again. Execute only that generated output.
- Use recursive SQLGlot scope analysis for CTEs, subqueries, joins, and set operations.
  Unknown relation-source shapes fail closed.
- Accept ordinary scalar and aggregate expressions without a recursive expression or
  function allowlist. The read-only role and object grants remain an independent
  backstop and must not grant unreviewed executable objects or alternate data sources.
- Accept structurally local `VALUES`, `GENERATOR`, and `FLATTEN` sources. A `FLATTEN`
  subquery still undergoes relation checks; a `GENERATOR` may not hide a nested query.
- Keep dynamic object identifiers, `RESULT_SCAN`, stages, custom table functions, and
  ambiguous source shapes rejected.
- Treat configured names as analyst-approved relation identities. Snowglobe does not
  perform catalog lookup or recursively inspect view and function definitions.
- Extend support by classifying SQLGlot AST shapes and adding accepted plus hostile
  tests. Never relax the one-query or approved-relation invariants merely to unblock a
  connected test.

## Consequences

- Snowglobe has a clear, explainable SQL governance feature rather than a brittle list
  of every allowed expression node.
- Legitimate analytics over approved views remain broad: functions, joins, CTEs,
  subqueries, aggregation, ordering, and set operations work.
- Some legitimate Snowflake relation features remain unsupported until their data
  provenance can be represented and tested. An equivalent approved-view query is the
  fallback during validation.
- The policy covers direct query syntax, not transitive dependencies or privileges;
  reviewed Snowflake views and least-privilege grants remain required.
- Generated-SQL reauthorization catches parser/generator class changes such as
  query-shaped input becoming a mutating statement.

The normative behavior and examples are in [the governed SQL policy](../sql-policy.md).
