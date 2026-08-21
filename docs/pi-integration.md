# Pi integration

**Verified against Pi 0.84.2 on August 19, 2026.** Pi evolves quickly; re-run
Snowglobe's checks when upgrading it.

Pi intentionally does not support MCP. Its supported equivalent is a TypeScript
extension that registers model-callable tools. Snowglobe therefore ships as a
[Pi package](https://pi.dev/docs/latest/packages) containing a
[Pi extension](https://pi.dev/docs/latest/extensions) that registers
`submit_read_query` and `get_query_status`. The extension provides strict
input schemas, sends SQL through stdin, validates the CLI's JSON independently, and
returns only the closed Snowglobe receipts.

## Architecture

```text
Pi model
   │ native typed tool call
   ▼
Snowglobe Pi extension
   │ uv run --project <installed package> snowglobe ...
   │ SQL on stdin; bounded receipt JSON on stdout
   ▼
Snowglobe CLI
   │ official MCP Streamable HTTP client on fixed loopback URL
   ▼
snowglobe-local ── control plane ── executor ── Snowflake
   │
   └── admitted result ── local viewer ── human analyst
```

The Pi package never starts another broker or executor. `snowglobe-local` must already
be running and remains the sole owner of credentials, request state, execution, and
result data.

## Prerequisites

Install Pi and Snowglobe's normal prerequisites:

```bash
npm install -g @earendil-works/pi-coding-agent
pi --version
uv --version
```

Set up, preflight, and launch Snowglobe first by following this guide's
[configuration and launch steps](getting-started.md#2-prepare-a-constrained-snowflake-environment).
Do not put the profile path, role, warehouse, key, or other Snowflake configuration in
Pi settings.

Pi packages execute arbitrary code with the current user's permissions. Review
[`integrations/pi/extensions/`](../integrations/pi/extensions) before installation, as
Pi's own package documentation recommends.

## Install

Install the exact clean revision you reviewed globally for all Pi projects:

```bash
test -z "$(git status --short)"
SNOWGLOBE_REF="$(git rev-parse HEAD)"
pi install "git:github.com/curtisalexander/snowglobe@${SNOWGLOBE_REF}"
pi list
```

On Windows PowerShell:

```powershell
if (git status --short) { throw "The checkout must be clean." }
$snowglobeRef = git rev-parse HEAD
pi install "git:github.com/curtisalexander/snowglobe@$snowglobeRef"
pi list
```

Or install only for the current trusted project:

```bash
test -z "$(git status --short)"
SNOWGLOBE_REF="$(git rev-parse HEAD)"
pi install "git:github.com/curtisalexander/snowglobe@${SNOWGLOBE_REF}" -l
pi list
```

On Windows PowerShell, use the preceding commands with `-l` appended to the
`pi install` command.

The commit pin is required for the connected MVP campaign. Record the same revision in
the private evidence template. An unpinned Git source follows a moving repository head
and is appropriate only when deliberately testing extension changes.

Project-local installation writes `.pi/settings.json`. Pi installs a missing package
after the project is trusted. Review that settings change before committing it; it
contains only the package source and must never contain Snowflake configuration.

Snowglobe is not published to the npm registry. The supported package sources are the
reviewed Git repository and a trusted local checkout.

To use an existing Snowglobe checkout without installing or copying files:

```bash
pi -e /absolute/path/to/snowglobe
```

On Windows, pass the checkout path such as `pi -e C:/src/snowglobe`.

This local-checkout form runs its current files, including uncommitted changes. Do not
use it for connected evidence unless that exact checkout was reviewed and recorded.

For extension development from this checkout:

```bash
pi -e ./integrations/pi/extensions/index.ts
```

Pi auto-discovers installed package resources at startup. In an already-running Pi
session, use `/reload` after changing a local extension.

## Use

Ask Pi:

> Use Snowglobe to submit `SELECT * FROM
> YOUR_TEST_DATABASE.YOUR_TEST_SCHEMA.YOUR_APPROVED_VIEW` with a TTL of 300 seconds. Poll until
> terminal and report only the receipts. Do not access the viewer or result stream.

Pi should call only:

1. `submit_read_query(sql, requested_ttl)`; then
2. `get_query_status(request_id)` until terminal.

Submission tool content is exactly:

```json
{"status":"accepted","request_id":"opaque-random-request-id","reason_code":"NONE"}
```

Status tool content is exactly:

```json
{"request_id":"opaque-random-request-id","status":"pending"}
```

When status reaches `complete`, inspect that ID yourself in the local viewer. Pi must
not read, summarize, or claim to have seen the result.

## Fail-closed behavior

The extension:

- invokes `uv` without a shell;
- reads no project or user Snowflake configuration;
- sends SQL to the CLI only through stdin;
- captures at most 4 KiB of stdout and never returns stderr;
- validates exact receipt keys, values, ID format, and accepted/rejected consistency;
- converts process launch, timeout, cancellation, nonzero exit, oversized output,
  malformed JSON, or an additional result-derived field to `SERVICE_UNAVAILABLE`; and
- exposes no result, viewer, cancellation, configuration, or credential tool.

This does not make the viewer inaccessible to Pi. Pi's generic `bash` and browser
capabilities run with the analyst's local permissions and may reach loopback routes.
The product guarantee remains channel separation: Snowglobe's native Pi tools do not
return result bytes or rich result metadata.

## Troubleshooting

| Symptom | Check |
|---|---|
| Tools are missing | Run `pi list`, confirm the package is enabled with `pi config`, then use `/reload` or restart Pi. |
| Submission returns `SERVICE_UNAVAILABLE` | Confirm `snowglobe-local` is running on its fixed loopback endpoint and was launched with the intended profile. Inspect startup or preflight diagnostics yourself; do not paste credentials or local diagnostics into Pi. |
| First call is slow | The Git-installed package may be creating its package-local locked Python environment with `uv` for the first time. |
| `uv` is not found | Install `uv` on `PATH`; do not point the extension at an unreviewed wrapper. |

## Update or remove

```bash
pi update --extensions
pi remove git:github.com/curtisalexander/snowglobe
```

Append `-l` to `remove` if the package was installed project-locally. Pinned Git refs
do not move during updates; install the desired new ref explicitly. Review changes
before updating because Pi extensions run with full local permissions.
