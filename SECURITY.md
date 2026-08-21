# Security

Snowglobe has one security boundary: query results do not travel through its
model-facing MCP, CLI, or Pi responses.

Those responses may contain only an opaque request ID, fixed submission status and
reason, and coarse lifecycle state. They must not contain rows, values, schema, names,
counts, sizes, timing, SQL, database errors, Snowflake identifiers, result locations,
or result-derived artifacts.

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

Until connected validation is complete, use only a dedicated non-production Snowflake
identity and non-sensitive test data. Do not include credentials or query results in
issues or transcripts.

See [PLAN.md](PLAN.md) and
[ADR 0018](docs/decisions/0018-minimal-boundary-cleanup.md).
