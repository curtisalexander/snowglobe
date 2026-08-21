# ADR 0010: Minimum Snowflake SELECT policy

- **Status:** Superseded by [ADR 0019](0019-relation-centric-sql-authorization.md);
  configuration ownership superseded by
  [ADR 0016](0016-separate-snowflake-and-snowglobe-configuration.md)
- **Date:** August 19, 2026
- **Builds on:** [ADR 0009](0009-constrained-snowflake-mvp-budgets.md)

This record preserves the original MVP policy. ADR 0019 replaces its `Select`-only
root, recursive expression allowlist, and function restrictions while retaining strict
single-query, approved-relation, literal-limit, and generated-SQL enforcement.

## Context

The connected MVP needs a parser-owned authorization boundary before model-authored SQL
can reach Snowflake. SQLGlot parsing alone is not authorization, and Querido's pinned
first-keyword scanner cannot recursively prove that CTEs, nested expressions, object
references, functions, or Snowflake-specific syntax are safe.

The MVP needs only enough SQL to prove the real query/result path. Broad function and
syntax support would increase policy surface without helping that proof.

## Decision

- Parse with SQLGlot's Snowflake dialect in raise-on-error mode and accept exactly one
  AST whose root is `Select`. Reject set-operation roots and every other statement
  class.
- Recursively allow only a small Snowglobe-owned set of SELECT, CTE, projection,
  predicate, join, ordering, grouping, literal, and arithmetic nodes. Any unknown or
  generic node fails closed.
- Require every external relation to be a fully qualified, unquoted
  `DATABASE.SCHEMA.VIEW` present in the profile's `allowed_views`. Submitted quoted
  identifiers are accepted only when their exact case resolves to the same configured
  identity.
- Use SQLGlot scope analysis to distinguish in-scope CTE references from unqualified
  external relations. Reject self-references that are not actually in scope, ambiguous
  unqualified external relations, and qualified columns whose source alias is absent.
- Keep the MVP function allowlist empty. Reject built-ins, context functions, UDFs,
  table functions, external functions, staged-file functions, and qualified function
  calls. A reviewed non-empty function allowlist can be added after the connected path
  is proven.
- Reject stages, file transfer, dynamic identifiers, variables, parameters, time
  travel, procedural SQL, metadata commands, DDL, DML, session changes, and generic
  parser fallback nodes.
- Require literal non-negative `LIMIT`, `FETCH`, and `OFFSET` values. Reject percent,
  ties, null, dynamic, and parameterized limits at every nesting level.
- Apply a server-owned top-level limit of 51 rows for the 50-row MVP budget. Preserve
  a smaller user limit; replace a larger literal limit. Generate Snowflake SQL from the
  modified AST, parse it again, and re-run the policy before execution.
- Raise only a detail-free policy rejection without retaining a chained parser error.

## Consequences

- The MVP can query approved views, project columns, filter, join approved sources,
  order, group, and use CTEs, but cannot call even ordinary aggregate or conversion
  functions yet.
- Fully qualified view names are intentionally less convenient but avoid relying on
  session search-path resolution at the authorization boundary.
- The 51st row proves overflow to later admission logic; it must never be published as
  a silently truncated 50-row result.
- Direct top-level limit replacement preserves ordering, offsets, and the semantics of
  smaller user limits for the accepted narrow grammar. Unsupported limit forms are
  rejected instead of wrapped textually.
- SQLGlot remains version-pinned, and parser upgrades require the hostile corpus and
  generated-SQL round-trip tests to pass before adoption.
