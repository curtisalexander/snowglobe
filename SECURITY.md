# Security

Snowglobe has one security boundary: query results do not travel through its
model-facing MCP, CLI, or Pi responses.

Submission responses may contain an opaque request ID, fixed status and reason, and the
exact governed SQL for accepted work (`null` when rejected). Lifecycle responses may
contain only the request ID and coarse state. Neither may contain rows, values, result
schema or column names, counts, sizes, timing, database errors, Snowflake identifiers,
result locations, or result-derived artifacts.

Result bytes travel through separate loopback viewer routes into a browser worker.
Enabling Snowglobe's MCP does not enable those routes or return their data. Browser,
screenshot, shell, and direct HTTP access are separate agent capabilities whose
availability is controlled by the agent host, not by the Snowglobe MCP contract.

Snowglobe relies on:

- the analyst and operating system to protect configuration and private-key files;
- a configured read-only Snowflake role to prevent mutation and unauthorized object
  access; and
- timeouts and bounded Arrow admission to control work and local memory.

Changes to MCP, CLI, or Pi schemas, output construction, errors, or transport require
exact-contract and result-canary tests. Changes to the viewer path require a test that
result canaries remain in the viewer path and absent from model-facing output.

Local preflight and startup commands are operator interfaces, not model-facing query
adapters, and may report configuration paths and validation details. Do not paste those
diagnostics into an agent conversation. Snowglobe suppresses the Snowflake connector's
own logger because its debug and exceptional paths can contain result payloads or result
locations.

Accepted MCP, CLI, and Pi submission receipts return the exact governed SQL because the
model authored the query and the harness needs to correlate the statement with its
request ID. Snowglobe does not retain SQL in broker metadata. The foreground local
runtime also prints the statement immediately before each connector execution attempt;
a terminal or service manager may capture it. Treat both interfaces as sensitive
because SQL may contain literals.

Until connected validation is complete, use only a dedicated non-production Snowflake
identity and non-sensitive test data. Do not include credentials or query results in
issues or transcripts.

See [PLAN.md](PLAN.md) and
[ADR 0021](docs/decisions/0021-return-governed-sql-in-submission-receipts.md).
