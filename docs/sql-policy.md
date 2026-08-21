# Governed SQL policy

Snowglobe's SQL policy is a product feature: an agent can write useful analytical SQL,
but Snowglobe executes only a regenerated read query whose direct external relations
are explicitly approved by the analyst.

The policy is intentionally **strict about statements and data sources** and
**permissive about read-query expressions**. This is the boundary Snowglobe can enforce
reliably without attempting to reproduce the Snowflake grammar or privilege system.

## Policy profile

Assume the local `snowglobe.toml` contains:

```toml
schema_version = 1

[profiles.default]
allowed_views = [
  "ANALYTICS.GOVERNED.CUSTOMER_BALANCES",
  "ANALYTICS.GOVERNED.CUSTOMER_EVENTS",
]
```

Configured names are exact, unquoted, uppercase `DATABASE.SCHEMA.VIEW` identities.
Every external relation in submitted SQL must resolve to one of them. Fully qualified
names avoid dependence on the session's current database, schema, or search path.

## What Snowglobe enforces

For every submission, Snowglobe:

1. parses with SQLGlot's Snowflake dialect in raise-on-error mode;
2. requires exactly one query-shaped statement;
3. traverses every SQLGlot scope and checks every direct external relation;
4. distinguishes lexical CTE references from external tables or views;
5. rejects unknown relation-source shapes rather than guessing;
6. applies a server-owned top-level `LIMIT 51` for the 50-row result budget;
7. generates Snowflake SQL from the authorized AST; and
8. parses and authorizes that generated SQL again before it can execute.

The second pass matters. For example, SQLGlot parses `SELECT ... INTO ...` as a query
but generates `CREATE TABLE ... AS SELECT`. Re-authorizing the generated statement
rejects that mutation.

Snowglobe executes the generated SQL, never the submitted text. The configured
read-only Snowflake role is an independent backstop against mutation and object access.

## Accepted examples

### Projection, filtering, aggregation, and ordering

```sql
SELECT region, SUM(balance) AS total_balance
FROM ANALYTICS.GOVERNED.CUSTOMER_BALANCES
WHERE active
GROUP BY region
ORDER BY total_balance DESC
```

Ordinary scalar and aggregate functions are accepted. Snowglobe adds `LIMIT 51` unless
the query already has a smaller literal limit.

### Joins and CTEs over approved views

```sql
WITH recent_events AS (
  SELECT customer_id, event_type
  FROM ANALYTICS.GOVERNED.CUSTOMER_EVENTS
  WHERE event_at >= DATEADD(day, -7, CURRENT_TIMESTAMP())
)
SELECT balances.customer_id, balances.balance, recent_events.event_type
FROM ANALYTICS.GOVERNED.CUSTOMER_BALANCES AS balances
JOIN recent_events USING (customer_id)
```

CTE names may be unqualified because SQLGlot resolves them lexically. Both external
relations still must be fully qualified and approved.

### Local rows and row expansion

These relation sources do not independently read a Snowflake object and are accepted:

```sql
SELECT * FROM (VALUES (1), (2)) AS local_values(value)
```

```sql
SELECT * FROM TABLE(GENERATOR(ROWCOUNT => 10))
```

```sql
SELECT balances.customer_id, flattened.value
FROM ANALYTICS.GOVERNED.CUSTOMER_BALANCES AS balances,
LATERAL FLATTEN(INPUT => balances.tags) AS flattened
```

`FLATTEN` may also contain a subquery, but every external relation inside that subquery
is checked normally. `GENERATOR` arguments may not hide a nested query.

## Rejected examples

| Input | Why it is rejected |
|---|---|
| `DROP TABLE ANALYTICS.RAW.CUSTOMERS` | DDL is not a query. |
| `DELETE FROM ANALYTICS.RAW.CUSTOMERS` | DML is not a query. |
| `CALL SEND_REPORT()` | Procedure calls are not queries. |
| `SELECT * INTO NEW_TABLE FROM ANALYTICS.GOVERNED.CUSTOMER_BALANCES` | Generated SQL is `CREATE TABLE AS SELECT`, so the generated-SQL pass rejects it. |
| `SELECT 1; SELECT 2` | More than one statement. |
| `SELECT * FROM ANALYTICS.RAW.CUSTOMERS` | The direct external relation is not approved. |
| `SELECT * FROM GOVERNED.CUSTOMER_BALANCES` | Partially qualified external relation. |
| `SELECT * FROM IDENTIFIER('ANALYTICS.RAW.CUSTOMERS')` | Dynamic object identity cannot be matched structurally to the allowlist. |
| `SELECT * FROM TABLE(RESULT_SCAN('query-id'))` | Alternate result source bypasses configured views. |
| `SELECT * FROM TABLE(UNREVIEWED_UDTF())` | Unknown table function may read another source. |
| `SELECT * FROM DIRECTORY(@stage)` | Stage-backed relation is not an approved view. |
| `SELECT * FROM ANALYTICS.GOVERNED.CUSTOMER_BALANCES JOIN ANALYTICS.RAW.CUSTOMERS USING (customer_id)` | One unapproved relation rejects the entire query. |
| `SELECT * FROM ANALYTICS.GOVERNED.CUSTOMER_BALANCES LIMIT $1` | The server cannot prove a dynamic limit is within its result budget. |

Policy rejection happens before a Snowflake connection is opened and produces only the
fixed model-facing reason `POLICY_REJECTED`.

## Exact guarantee and deliberate limits

The policy guarantees that the SQL Snowglobe sends to Snowflake is one query and that
every **direct relation named by that query** is approved or is one of the structurally
local row sources above.

It does not claim to:

- inspect the definition or transitive dependencies of an approved view;
- query the Snowflake catalog to prove that a configured identity is a view rather
  than another selectable relation;
- inspect the implementation of scalar UDFs or external functions;
- replace Snowflake grants with an application-side privilege system; or
- prove that an accepted query is cheap. Timeouts and result limits handle boundedness.

The analyst should therefore configure actual governed views and a role that has
`SELECT` only on those views. Do not grant that role unreviewed tables, UDFs, external
functions, procedures, stages, or integrations. Scalar expressions and functions stay
available because recursively allowlisting every Snowflake expression would create a
large compatibility project without strengthening direct relation enforcement.

## How to handle an unsupported edge case

Do not weaken the one-query or approved-relation invariants to get a connected test to
pass. Classify the rejected SQL instead:

1. If it is only a new expression under an already approved query source, support it
   without creating a recursive expression allowlist.
2. If it is a new relation-source shape, inspect its SQLGlot AST and add support only
   when Snowglobe can identify every external relation or prove that the source is
   local, as with `VALUES`, `GENERATOR`, or `FLATTEN`.
3. If its provenance remains ambiguous, keep it rejected and use an equivalent query
   over approved views for the connected test.

Every extension needs an accepted example, hostile variants that hide an unapproved
relation, and a generated-SQL round-trip test. SQLGlot upgrades must run the complete
policy corpus. Regexes, first-keyword checks, and blanket unknown-source fallbacks are
not acceptable substitutes for AST review.

See [ADR 0019](decisions/0019-relation-centric-sql-authorization.md) for the decision
behind this posture.
