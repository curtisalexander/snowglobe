# Snowglobe

<p align="center">
  <img src="assets/snowglobe-logo.webp" alt="A duck, snowflake, and streams of data contained inside a snow globe" width="420">
</p>

**A local Snowflake query MCP and result viewer for one analyst.**

**New here? Follow the [getting-started guide](docs/getting-started.md)** from clone
through Snowflake configuration, preflight, launch, MCP client setup, and the first
viewer result.

**Reviewing or extending the code? Read the [developer guide](docs/developer-guide.md)**
for the architecture, end-to-end call paths, file ownership, invariants, and suggested
code-review order.

Snowglobe lets a coding agent submit governed read-only SQL without putting the query
result into a model-facing response. Agents may use MCP directly or, when they do not
support MCP, call the result-free `snowglobe` CLI. Submission runs asynchronously and
returns the exact governed SQL with an opaque request ID. The agent may poll that ID for
a small lifecycle state, while the analyst uses the same ID in a local viewer to inspect
the result.

```text
                       MCP or CLI — control only
┌──────────────┐     ┌─────────────────────────┐     ┌───────────┐
│ Analyst's    │────▶│ local Snowglobe runtime │────▶│ Snowflake │
│ coding agent │◀────│ submit + status         │     │           │
└──────────────┘     └────────────┬────────────┘     └─────┬─────┘
    governed SQL + ID + lifecycle │                        │
                                  │ shared local broker    │
                                  ▼                        │
                       ┌──────────────────────┐            │
                       │ local viewer backend │◀───────────┘
                       └──────────┬───────────┘
                                  │ admitted Arrow stream
                                  ▼
                       ┌──────────────────────┐
                       │ browser worker       │
                       │ + DuckDB-Wasm        │
                       └──────────────────────┘
```

There are no viewer accounts, enterprise OIDC, tenants, owner claims, or sharing. MCP
and viewer routes run in one process and bind to loopback for individual use.

## Status

Snowglobe is implementation-complete for external connected-MVP validation, but that
validation has not yet been performed. It is **not ready for production credentials,
sensitive data, or routine analyst use**. One dedicated non-production test credential
is permitted only under the [constrained MVP runbook](docs/constrained-mvp-runbook.md).
Implemented pieces include:

- explicit low-level MCP contracts for `submit_read_query` and
  `get_query_status`;
- a transport-neutral control plane and result-free CLI for Pi and other shell-only
  agents;
- an installable Pi package with two native typed tools;
- a single-analyst broker with pending, complete, failed, cancelled, and expired
  lifecycle states and at most 100 active/recent records;
- a configured background Snowflake executor that fetches incrementally and publishes
  only admitted results;
- local viewer routes to list, find, and stream a request;
- incremental Arrow admission and failure-atomic framing; and
- in-memory DuckDB-Wasm ingestion with a bounded main-thread viewport.

The submit tool returns `SERVICE_UNAVAILABLE` unless the supported launcher is
explicitly given a local configuration file. The real executor, browser worker path,
and [connected validation runbook](docs/constrained-mvp-runbook.md) now exist.

- [Implementation plan](PLAN.md)
- [Connected MVP validation runbook](docs/constrained-mvp-runbook.md)
- [Getting started](docs/getting-started.md)
- [Developer architecture and review guide](docs/developer-guide.md)
- [Governed SQL policy and examples](docs/sql-policy.md)
- [Boundary-focused MVP evidence template](docs/mvp-evidence-template.md)
- [Single-analyst architecture decision](docs/decisions/0008-single-analyst-loopback-runtime.md)
- [Threat model](docs/threat-model.md)
- [Security policy](SECURITY.md)
- [Documentation index](docs/README.md)

## Boundary

MCP and the result-free CLI may return only:

- an accepted/rejected submission receipt with an opaque request ID, fixed reason, and
  exact governed SQL for accepted work (`null` when rejected); or
- an opaque request ID plus `pending`, `complete`, `failed`, `cancelled`, `expired`,
  `not_found`, or `service_unavailable`.

Neither adapter may return rows, schema, column names, counts, sizes, timing, Snowflake
query IDs, database errors, result URLs, or result-derived artifacts. Result bytes
travel only through the local viewer backend into the browser worker.

Enabling Snowglobe's MCP enables only its result-free submission and lifecycle tools;
it does not grant access to the viewer routes. Browser, screenshot, shell, and direct
HTTP access are separate agent capabilities controlled by the agent host.

## Local development

The credential-bearing MVP runtime supports Linux, macOS, and native Windows 10/11.
Snowglobe trusts the analyst and operating system to manage file access. All platforms
require Python 3.12 with `uv`, plus Node.js 22.19 or newer and npm.

From a fresh clone, install the exact locked dependencies, including the optional
Snowflake connector:

```bash
./scripts/setup-dev.sh
```

On Windows PowerShell, run `./scripts/setup-dev.ps1` instead.

Run the complete connection-free suite with one command:

```bash
./scripts/check-dev.sh
```

On Windows PowerShell, run `./scripts/check-dev.ps1` instead.

To start in fail-closed development mode without Snowflake execution:

```bash
# One loopback process owns MCP, viewer routes, and the in-memory broker.
uv run snowglobe-local

# In another terminal; Vite proxies viewer API calls to the local runtime.
npm run dev
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`. Do not launch the MCP and viewer
backend as separate processes while the broker is in memory, and do not bind either
service to `0.0.0.0`.

Agents without MCP support can call that same running service through the CLI. SQL is
read from standard input and stdout contains exactly one closed JSON receipt:

```bash
uv run snowglobe submit \
  --ttl 300 <<'SQL'
SELECT * FROM TEST_DATABASE.TEST_SCHEMA.APPROVED_VIEW
SQL

uv run snowglobe status '<opaque-request-id>'
```

You do not need to create a SQL file. An MCP-capable agent drafts SQL from your
description and sends it in the `sql` field of `submit_read_query`; Snowglobe itself
does not translate natural language into SQL. The CLI likewise accepts any standard
input, so a heredoc, pipe, or redirected file is only a caller preference.

The accepted MCP, CLI, and Pi submission receipt includes the opaque request ID and the
exact governed SQL being attempted. This is the SQLGlot-regenerated statement after
policy checks and the server-owned row cap, so it may differ in formatting and limit
from the agent's draft. The foreground `snowglobe-local` terminal also prints both
immediately before each connector call. Because SQL can contain sensitive literals,
protect model transcripts, terminal captures, and service logs accordingly.

The CLI does not run a second executor and has no result-reading command. It requires
`snowglobe-local` to remain running because the daemon owns the in-memory request and
result state.

For native Pi tools instead of shell commands, install the reviewed package:

```bash
test -z "$(git status --short)"
SNOWGLOBE_REF="$(git rev-parse HEAD)"
pi install "git:github.com/curtisalexander/snowglobe@${SNOWGLOBE_REF}"
```

The clean-checkout commit pin is required for the connected MVP campaign because Pi
packages execute with the analyst's permissions. An unpinned Git install is suitable
only for deliberate extension development.

See the [Pi integration guide](docs/pi-integration.md) for global and project-local
installation, verification, usage, security behavior, updates, and removal.

The development check script runs:

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
npm run lint
npm run typecheck
npm test
npm run build
```

For the connected test, follow the [constrained MVP runbook](docs/constrained-mvp-runbook.md)
before starting either process. The Snowflake executor reads a native local
`connections.toml` profile and a matching Snowglobe policy profile from
`snowglobe.toml`. Start from [`connections.example.toml`](connections.example.toml)
and [`snowglobe.example.toml`](snowglobe.example.toml); never commit the real files or
private key. Store them according to your normal local secret-management practice;
Snowglobe does not inspect file ownership or permissions.

Validate the local profile and key without connecting to Snowflake. Failures include
local configuration details so the analyst can correct them; these operator diagnostics
are not returned by MCP, the result-free CLI, or Pi.

```bash
uv run snowglobe-preflight \
  --connections connections.toml \
  --snowglobe-config snowglobe.toml \
  --profile default
```

The explicit `--connect` mode is permitted only by the constrained MVP test procedure.
It opens and closes one Snowflake cursor and executes no SQL. Preflight reports each
check as it starts and ends with a fixed pass/fail message; see the runbook for expected
timing and connected-check scope.

The local service's `--connections connections.toml --snowglobe-config snowglobe.toml
--profile default` options explicitly enable configured execution. They are likewise
reserved for the Gate 5 procedure; starting without both configuration options remains
fail-closed. The connected procedure must install the optional connector first; both
setup workflows do so. The MCP-only workflow excludes development dependencies with
`uv sync --locked --no-dev --extra snowflake`.

`snowglobe-local` reports its startup phases, starts a loopback server, and then remains
running in the foreground until `Ctrl-C`. Startup validates local configuration and key
material but does not connect to Snowflake; connections are opened only for submitted
queries.

The constrained MVP accepts one pending request for at most five minutes. Connection
timeouts are 30 seconds for login, 60 seconds for network retries, and 15 seconds per
socket operation. Snowflake statements have a 60-second server deadline and a
15-second queue deadline. Results are limited to 50 rows, 32 columns, 16 KiB per cell,
and 256 KiB serialized and decoded Arrow so the complete admitted result fits the
current viewer.

Each Snowglobe policy profile has an exact `allowed_views` list. MVP queries must
reference those views as fully qualified `DATABASE.SCHEMA.VIEW` names. Snowglobe
accepts ordinary read-query expressions and functions; the configured read-only role
is responsible for preventing mutation and unauthorized object access. Local
`GENERATOR` and `FLATTEN` row sources are accepted; alternate data sources such as
`RESULT_SCAN`, stages, and custom table functions are not.

The [governed SQL policy](docs/sql-policy.md) documents the precise guarantee,
accepted and rejected examples, generated-SQL reauthorization, deliberate limits, and
the rule for adding new Snowflake syntax without weakening relation enforcement.

Use the [getting-started guide](docs/getting-started.md) for the complete clone,
Snowflake profile, preflight, launch, Amp, Codex, Claude Code, Continue.dev, first-query,
and viewer workflow.

## License

[MIT](LICENSE) © 2026 Curtis Alexander
