# ADR 0014: Package Snowglobe as two native Pi tools plus a workflow skill

- **Status:** Accepted
- **Date:** August 19, 2026
- **Builds on:** [ADR 0013](0013-result-free-cli-adapter.md)

## Context

Pi does not support MCP, but its current extension API can register TypeScript tools
that are directly callable by the model. Pi skills provide on-demand instructions but
do not define a typed execution boundary: a skill-only integration would tell the
model to assemble shell commands and parse their output with the generic `bash` tool.

Snowglobe needs Pi to see exactly the existing submission and lifecycle receipts. The
integration must not expose viewer routes, raw subprocess output, stderr, result data,
or richer failures. It must also remain installable through Pi's supported package
manager rather than requiring users to copy files into Pi's configuration directory.

## Decision

- Make the Snowglobe repository root a Pi package with a `package.json` `pi` manifest.
- Register exactly two native Pi tools named `submit_read_query` and
  `get_query_status`, matching the MCP names and input shapes.
- Have the extension invoke the package-local Python CLI through `uv run --project`
  with `--frozen`. Use argument arrays without a shell and send SQL only through the
  child process's stdin.
- Bound captured output, discard stderr, honor tool cancellation and fixed timeouts,
  parse stdout as untrusted JSON, and independently enforce exact receipt fields,
  enums, request-ID shape, and submission-state consistency.
- Map launch, transport, timeout, cancellation, overflow, malformed output, and
  validation failures to a fresh closed `SERVICE_UNAVAILABLE` receipt. Never throw a
  private subprocess error into Pi's tool-error channel.
- Return only compact receipt JSON in Pi tool text content. Keep tool details empty.
- Bundle a small `snowglobe` skill for progressive-disclosure workflow instructions.
  The extension is the capability boundary; the skill is guidance, not enforcement.
- Do not register result, viewer, cancellation, configuration, preflight, or
  credential tools.

## Consequences

- Users can install the integration globally or per project with `pi install` from the
  Snowglobe Git repository, and Pi discovers both tools and the skill.
- Pi receives native typed tool definitions instead of relying on the model to compose
  `bash` commands.
- The installed Pi package needs `uv`; its package-local Python environment acts only
  as an MCP client. The separately launched `snowglobe-local` process remains the sole
  broker, executor, credential, and viewer owner.
- Pi extensions execute with the analyst's OS permissions. This integration preserves
  Snowglobe's automatic control-channel boundary but does not prevent Pi's generic
  tools from reaching loopback viewer routes. The skill and tool guidance tell Pi not
  to do so; they are not an isolation boundary.
- Pi API upgrades are security-sensitive and require type checks, package-load tests,
  and boundary-canary review.

## Required evidence

Tests must verify:

- exactly two tools are registered with closed parameter objects;
- SQL reaches the child only through stdin and no shell is used;
- stdout and stderr are bounded and stderr is never returned;
- exact valid receipts pass unchanged;
- additional fields, malformed JSON, inconsistent states, oversized output, nonzero
  exit, timeout, and cancellation fail closed; and
- submitted SQL, purpose, result canaries, and private errors never appear in the Pi
  tool result.
