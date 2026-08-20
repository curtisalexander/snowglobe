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
returns an opaque request ID. The agent may poll that ID for a small lifecycle state,
while the analyst uses the same ID in a local viewer to inspect the result.

```text
                       MCP or CLI — control only
┌──────────────┐     ┌─────────────────────────┐     ┌───────────┐
│ Analyst's    │────▶│ local Snowglobe runtime │────▶│ Snowflake │
│ coding agent │◀────│ submit + status         │     │           │
└──────────────┘     └────────────┬────────────┘     └─────┬─────┘
       opaque ID + lifecycle      │                        │
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
- an installable Pi package with two native typed tools and a workflow skill;
- a single-analyst broker with pending, complete, failed, cancelled, and expired
  lifecycle states;
- a configured background Snowflake executor that registers a request-scoped cursor
  before acceptance, fetches incrementally, and publishes only admitted results;
- local viewer routes to list, find, cancel, and stream a request;
- incremental Arrow admission and failure-atomic framing; and
- in-memory DuckDB-Wasm ingestion with a bounded main-thread viewport.

The submit tool returns `SERVICE_UNAVAILABLE` unless the supported launcher is
explicitly given a local configuration file. The real executor and minimum browser
boundary assurance and the [Gate 5 constrained-test runbook](docs/constrained-mvp-runbook.md)
now exist. `SECURITY.md` authorizes only that constrained connected test.

- [Implementation plan](PLAN.md)
- [Constrained MVP test runbook](docs/constrained-mvp-runbook.md)
- [Getting started](docs/getting-started.md)
- [Developer architecture and review guide](docs/developer-guide.md)
- [Value-free MVP evidence template](docs/mvp-evidence-template.md)
- [Single-analyst architecture decision](docs/decisions/0008-single-analyst-loopback-runtime.md)
- [Threat model](docs/threat-model.md)
- [Security policy](SECURITY.md)
- [Documentation index](docs/README.md)

## Boundary

MCP and the result-free CLI may return only:

- an accepted/rejected submission receipt with an opaque request ID and fixed reason;
  or
- an opaque request ID plus `pending`, `complete`, `failed`, `cancelled`, `expired`,
  `not_found`, or `service_unavailable`.

Neither adapter may return rows, schema, column names, counts, sizes, timing, Snowflake
query IDs, database errors, result URLs, or result-derived artifacts. Result bytes
travel only through the local viewer backend into the browser worker.

Loopback is not authentication or process isolation. A coding agent with arbitrary
same-host HTTP, browser, shell, or process access may be able to call the local viewer
backend or capture rendered data. Snowglobe prevents an automatic result-bearing
control channel; it does not claim to defend the analyst's data from other processes
running as that analyst.

## Local development

The credential-bearing MVP runtime supports Linux, macOS, and native Windows 10/11.
Windows credential files must be on local NTFS storage so Snowglobe can enforce owner,
ACL, and reparse-point checks. All platforms require Python 3.12 with `uv`, plus
Node.js 22.12 or newer and npm.

From a fresh clone, install the exact locked dependencies, including the optional
Snowflake connector:

```bash
./scripts/setup.sh
```

On Windows PowerShell, run `./scripts/setup.ps1` instead.

Run the complete connection-free suite with one command:

```bash
./scripts/check.sh
```

On Windows PowerShell, run `./scripts/check.ps1` instead.

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
  --purpose "Constrained Snowglobe MVP canary check" \
  --ttl 300 <<'SQL'
SELECT * FROM TEST_DATABASE.TEST_SCHEMA.APPROVED_VIEW
SQL

uv run snowglobe status '<opaque-request-id>'
```

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

The check script runs:

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
private key. Snowglobe accepts all three only when they are regular files owned by the
current user, are not symlinks or Windows reparse points, and grant no access to
unprivileged other users. On POSIX, the owner must have read permission and may have
write permission (`0400` or `0600`):

```bash
chmod 600 connections.toml snowglobe.toml /path/to/snowflake-key.p8
```

On Windows, remove inherited ACL entries and grant only your account read/write access
(Local System and Administrators remain privileged like POSIX root):

```powershell
$account = "$env:USERDOMAIN\$env:USERNAME"
icacls C:\private\connections.toml /inheritance:r /grant:r "${account}:(R,W)"
icacls C:\private\snowglobe.toml /inheritance:r /grant:r "${account}:(R,W)"
icacls C:\private\snowflake-key.p8 /inheritance:r /grant:r "${account}:(R,W)"
```

Validate the local profile and key without connecting to Snowflake:

```bash
uv run snowglobe-preflight \
  --connections connections.toml \
  --snowglobe-config snowglobe.toml \
  --profile default
```

The explicit `--connect` mode is permitted only by the constrained MVP test procedure.
It opens and closes one Snowflake cursor, executes no SQL, and prints only a fixed
pass/fail message.

The local service's `--connections connections.toml --snowglobe-config snowglobe.toml
--profile default` options explicitly enable configured execution. They are likewise
reserved for the Gate 5 procedure; starting without both configuration options remains
fail-closed. The connected procedure must install the optional connector first; the
setup script does so with `uv sync --locked --extra snowflake`.

The constrained MVP accepts one pending request for at most five minutes. Connection
timeouts are 30 seconds for login, 60 seconds for network retries, and 15 seconds per
socket operation. Snowflake statements have a 60-second server deadline and a
15-second queue deadline. Results are limited to 50 rows, 32 columns, 16 KiB per cell,
and 256 KiB serialized and decoded Arrow so the complete admitted result fits the
current viewer.

Each Snowglobe policy profile has an exact `allowed_views` list. MVP queries must
reference one of those views as a fully qualified `DATABASE.SCHEMA.VIEW`. The initial
function allowlist is intentionally empty: functions, UDFs, table functions, stages,
variables, and partially qualified relations are rejected until separately reviewed.

Use the [getting-started guide](docs/getting-started.md) for the complete clone,
Snowflake profile, preflight, launch, Amp, Codex, Claude Code, Continue.dev, first-query,
and viewer workflow.

## License

[MIT](LICENSE) © 2026 Curtis Alexander
