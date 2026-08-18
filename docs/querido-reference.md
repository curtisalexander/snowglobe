# Querido reuse audit

**Reviewed baseline:** Querido commit `eb6879e80a09acd0a4c090c42801d68f7fc101d9` (July 28, 2026)

Querido proves much of the basic Python connection path Snowglobe needs, but it is an interactive exploration CLI with intentionally model-visible results. Snowglobe should adapt a few focused patterns into Snowglobe-owned modules—not depend on Querido as a package or copy its general application machinery.

## Executive reuse map

| Area | Querido source | Snowglobe decision |
|---|---|---|
| TOML parsing and schema version | `src/querido/config.py:15-62` | Adapt the small `tomllib`/version-check pattern with a strict Snowglobe schema |
| Atomic config writing | `src/querido/config.py:65-95` | Do not ship initially; Snowglobe reads operator-managed configuration only |
| Profile/path resolution | `src/querido/config.py:275-361` | Keep server-selected named profiles and `~` expansion; drop local DB inference and user selection |
| Connector construction | `src/querido/connectors/factory.py:9-63` | Do not copy the generic factory; build one explicit Snowflake constructor |
| JWT private key conversion | `src/querido/connectors/snowflake.py:35-70` | Adapt PEM-then-DER loading and PKCS#8 DER serialization, with added validation/tests |
| Driver connection | `src/querido/connectors/snowflake.py:78-92` | Adapt explicit connection creation; pass only allowlisted Snowglobe fields |
| Cursor ownership | `src/querido/connectors/snowflake.py:134-189` | Adapt per-execution cursor cleanup and active-cursor registration |
| Arrow retrieval | `src/querido/connectors/snowflake.py:161-189,445-453` | Use `fetch_arrow_batches()` only; replace buffering/concatenation with incremental IPC streaming |
| Cancellation | `src/querido/connectors/snowflake.py:420-443` | Adapt best-effort cursor cancellation, scoped to one request rather than every cursor on a shared connector |
| Identifier validation | `src/querido/connectors/base.py:4-54` | Reuse the allowlist idea for configuration/policy identifiers; let the Snowflake AST parser own submitted SQL identifiers |
| Driver error types | `src/querido/connectors/base.py:62-159` | Reuse typed internal categories, but never preserve raw driver text in model-facing exceptions |
| Read-only SQL tests | `src/querido/core/sql_safety.py`, `tests/test_query.py:436-509` | Reuse adversarial cases as seed fixtures; do not reuse the scanner as the security parser |
| Outer limit | `src/querido/core/query.py:87-94` | Reuse the ceiling concept only; implement an AST transformation with `K + 1` overflow detection |
| Snowflake connector mocks | `tests/test_snowflake.py:1-78` | Adapt fake connection/cursor/Arrow-batch seams and add missing lifecycle/security cases |
| Tooling | `pyproject.toml` | Adopt Python 3.12+, uv, pytest, Ruff, and ty for backend components |
| Proposed MCP wrapper | `docs/research/mcp-wrapper-design.md` | Do not reuse subprocess/envelope/result behavior; only retain the small curated-tool principle |

## Configuration findings

Querido's loader usefully:

- parses TOML with the standard-library `tomllib`;
- handles a top-level `schema_version` and rejects versions newer than it understands;
- requires `[connections]` to be a mapping;
- supports a named profile and expands `~` in paths; and
- writes atomically with a same-directory temporary file, rename, and `0600` mode.

Snowglobe needs a narrower read-only loader:

1. Resolve the configuration file from one server deployment setting, with a documented local-development default.
2. Fail closed when the file, `[connections]`, selected profile, or required field is absent.
3. Reject unknown root/profile fields instead of forwarding arbitrary TOML to the Snowflake driver.
4. Require exactly `account`, `user`, `authenticator`, `private_key_path`, `db`, `warehouse`, and `role` for the first schema.
5. Require `authenticator = "SNOWFLAKE_JWT"`.
6. Select the profile from server configuration; never accept it in MCP input.
7. Map `db` to the driver's `database` argument.
8. Validate that the config and key paths satisfy deployment file-permission policy without assuming every container secret mount uses Unix `0600`.
9. Never expose config listing, cloning, writing, or “test connection” through MCP.

Querido does **not** check permissions when reading either file, reject unknown profile fields, or test the private-key path. Those are new Snowglobe requirements.

## Private-key handling findings

The reusable algorithm in Querido is:

1. expand `private_key_path`;
2. read the key bytes;
3. attempt `load_pem_private_key`;
4. fall back to `load_der_private_key` on format/algorithm failure; and
5. serialize the key as unencrypted PKCS#8 DER for `snowflake.connector.connect`.

Snowglobe should extract this into a small function that:

- verifies the path and key are readable under server policy;
- accepts only an RSA private key compatible with Snowflake key-pair authentication;
- does not accept a passphrase from TOML (a later passphrase must come from a secret provider);
- returns a generic internal configuration/authentication category on failure;
- never includes key bytes, path, cryptography exception text, or driver text in MCP output;
- drops references promptly while acknowledging that Python cannot guarantee zeroization of immutable byte buffers; and
- is covered with generated temporary RSA keys in PEM and DER PKCS#8 formats, malformed data, an encrypted key without a supplied secret, a missing path, and an unsupported key type.

Querido currently has no focused tests for this loader. Its `cryptography` dependency appears only in the development group even though the runtime path imports it; Snowglobe must declare it as a backend runtime dependency.

## Connection construction findings

Querido forwards a flexible `**kwargs` dictionary after removing application-specific keys. Snowglobe should instead construct driver arguments explicitly:

```text
account
user
authenticator = SNOWFLAKE_JWT
private_key = loaded PKCS#8 DER bytes
database = configured db
warehouse
role
session_parameters = server-owned controls
application = Snowglobe identifier, if supported by the pinned driver
```

Do not copy Querido's `client_store_temporary_credential = true` or `client_request_mfa_token = true` defaults. They serve interactive SSO/MFA and are inappropriate for a non-interactive JWT service identity.

Querido does not configure or test:

- `QUERY_TAG`;
- statement or queued-statement timeout session parameters;
- detached-query behavior;
- login/network timeout;
- connection pooling or request isolation;
- persisted query result retrieval; or
- `RESULT_SCAN`.

Snowglobe must spike these against the pinned Snowflake connector. Query tags may contain only opaque application/request identifiers. They must not contain user names, SQL, prompts, object names, or customer identifiers.

## Execution and Arrow findings

Useful Querido lifecycle behavior:

- create one cursor per execution;
- register it while active;
- always remove and close it in `finally`;
- keep connection cleanup behind a context manager; and
- call `cursor.cancel()` as a best-effort interruption.

Unsafe behavior for Snowglobe:

- `list(cursor.fetch_arrow_batches())` buffers the full result;
- `pyarrow.concat_tables(...)` creates a complete server-side analytical copy;
- column names are lowercased for Querido's internal dictionary contract;
- `to_pylist()` materializes all rows as Python objects;
- standard `fetchall()` is used as an Arrow fallback; and
- a connector-wide `cancel()` cancels every tracked cursor.

Snowglobe's executor must instead:

1. bind one execution/cursor handle to one opaque request ID and authenticated owner;
2. preserve Snowflake/Arrow field names and types on the human data path;
3. iterate Arrow tables/batches incrementally;
4. inspect each batch before release and update row, column, cell, Arrow-byte, and memory estimates;
5. write Arrow IPC incrementally with backpressure;
6. stop fetching and cancel/close on any limit, disconnect, expiry, or explicit cancellation;
7. fail the human-visible request if Arrow retrieval is unavailable rather than falling back to rows;
8. expose no completion, schema, size, overflow, or driver detail to MCP; and
9. make cancellation idempotent and request-scoped so one request cannot affect another.

An empty result still needs a valid human-path schema/completion contract. Querido's empty `pa.table({})` loses schema information, so this behavior cannot be copied.

## SQL policy findings

Querido's SQL safety scanner is thoughtfully quote/comment aware and fails closed on malformed input. Its tests cover:

- CTE-prefixed `DELETE`, `UPDATE`, `INSERT`, and safe `SELECT`;
- multiple statements and semicolons inside strings;
- line/block comments and unterminated input;
- `COPY`, `EXPORT`, `ATTACH`, `DETACH`, `INSTALL`, `LOAD`, `CALL`, and `VACUUM`;
- `PUT`, `EXECUTE IMMEDIATE`, and pragma-like statements; and
- `EXPLAIN ANALYZE` targets.

This is valuable as a regression corpus, but not as Snowglobe's enforcement mechanism. It recognizes first keywords rather than a Snowflake AST, permits multiple read statements, and permits `VALUES`, `SHOW`, `DESCRIBE`, and `EXPLAIN`. It cannot prove that a `SELECT` avoids an external function, dangerous UDF, disallowed object, or dynamic behavior.

Snowglobe will:

- accept exactly one AST-parsed `SELECT` or `WITH … SELECT`;
- allowlist object and function nodes;
- reject every other statement class;
- use the Snowflake role as an independent backstop; and
- port Querido's hostile SQL examples into parser-policy tests, adding Snowflake scripting, stages, table functions, external functions, quoted identifiers, and nested constructs.

Querido's `select * from (<sql>) … limit N` wrapper illustrates a useful ceiling but does not detect truncation and is not AST-safe. Snowglobe must transform the validated AST to request `K + 1`, preserve ordering and existing limits, and reject overflow before publishing the result.

## Identifier and metadata findings

Querido validates plain dotted identifiers and quotes each segment separately. This is a good rule for Snowglobe-owned identifiers such as configured database/warehouse/role names and generated aliases. It deliberately rejects valid quoted names containing spaces, hyphens, `$`, or Unicode.

Submitted SQL must not be normalized with this helper. The AST parser must preserve quoted-identifier semantics and compare canonical object/function identities against policy.

Querido also contains useful Snowflake catalog patterns in `SnowflakeConnector._resolve_table`, `get_tables`, and `get_columns`, including fully qualified names and bound metadata values. These are **not** needed for the base query/result path. They may inform a later operator-side allowlist validator or separately approved metadata catalog, but must never become an implicit model-visible schema tool.

Do not copy `get_row_count`'s `count(*)` fallback for views into admission. It can turn metadata inspection into an unbounded scan. Snowglobe's compute and result gates remain independent.

## Error and logging findings

Querido's typed `ConnectorError` categories and final code mapping are useful structural ideas. Its payloads are intentionally unsuitable for Snowglobe because they retain raw driver messages, identifiers, SQL, recovery hints, and the last executed statement. Its debug pipeline also logs the configured account.

Snowglobe needs two separate error boundaries:

- **Agent boundary:** only `INVALID_REQUEST`, `POLICY_REJECTED`, or `SERVICE_UNAVAILABLE`; no raw exception, SQL, object, account, path, status, completion, timing, or traceback.
- **Human/operator boundary:** a separately authorized status and restricted operational record, still redacted and value-free. Full driver messages require an explicit restricted diagnostic policy rather than ordinary logs.

Typed internal exceptions should carry a stable category and opaque request ID, not raw driver prose as their public message. The final MCP serializer must discard every unapproved field even if an internal exception was constructed incorrectly.

## Testing patterns to adapt and extend

Querido's `tests/test_snowflake.py` demonstrates a fast seam: inject a fake `snowflake.connector`, return mock connections/cursors, and feed typed PyArrow tables. Snowglobe should retain this approach while testing its different contract.

Required focused tests:

- strict TOML schema/version/profile selection and unknown-field rejection;
- absent/malformed config without path or parser detail in MCP output;
- generated PEM and DER RSA key loading plus all failure cases listed above;
- exact driver keyword allowlist and `db` → `database` mapping;
- no interactive credential-cache/MFA flags;
- configured role/warehouse cannot be overridden by tool input;
- cursor registration, closure, and connection cleanup on success and every failure point;
- incremental consumption proves the second batch is not requested before the first is admitted/forwarded;
- no `list`, concatenation, dictionary, or standard-row fallback path;
- Arrow field names/types and empty-schema preservation;
- per-batch row/byte/cell/memory overflow and final-batch overflow;
- client disconnect, expiry, explicit cancellation, cancellation error, and idempotent repeated cancellation;
- two simultaneous owners cannot stream or cancel each other's request;
- raw SQL, literals, driver messages, account, role, warehouse, and key path cannot appear in MCP/log captures;
- the strict receipt remains byte/schema bounded under arbitrary internal exceptions; and
- the ported adversarial SQL corpus is rejected or accepted by AST policy for the intended reason.

Tests must not merely import Querido's suite: its expected lowercase columns, buffered tables, dictionary fallback, raw errors, and CLI output are explicitly the wrong Snowglobe behavior.

## Code and machinery not to copy

- generic SQLite/DuckDB/Snowflake connector protocol and factory;
- qdo CLI config add/list/clone/remove/test commands;
- CLI output envelopes, `next_steps`, SQL echoing, and error hints;
- metadata, cache, catalog, profile, session, report, TUI, or workflow layers;
- connector-wide cancellation and concurrent profile-query machinery;
- Arrow concatenation, lowercase-column normalization, `to_pylist`, and `fetchall` fallback;
- qdo SQL classification as the primary parser;
- qdo's allow-write path, query planning, estimates, or unbounded `limit = 0` option;
- credential caching intended for interactive SSO/MFA;
- subprocess-per-tool-call MCP wrapping; and
- model-visible catalog, context, preview, values, quality, or profile tools.

If implementation copies a substantial code fragment rather than merely adapting an idea, preserve appropriate source attribution. Snowglobe and Querido are both MIT-licensed, but provenance should remain reviewable.
