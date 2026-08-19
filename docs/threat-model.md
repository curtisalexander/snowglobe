# Synthetic proof threat model

**Status:** Milestone 1 base product model with optional certified-deployment extension
**Last updated:** August 19, 2026

This document is the test design for the synthetic proof, not a production identity
or storage architecture. Internal claim types, the test-only in-process broker,
injected Result API authentication/authorization seams, and synthetic Arrow admission
are implemented. MCP still rejects submissions, the default Result API authenticator
denies all result access, and no real token authentication or Snowflake source is
connected.

## Security claims

### Base product claim

For the synthetic proof, result canaries may reach only the authenticated human's
Result API response and ephemeral viewer worker through Snowglobe-owned interfaces.
The agent receives the closed MCP receipt in `PLAN.md`; result status, metadata,
schemas, values, errors, and data-plane locations do not cross MCP. Agent and service
identities cannot authenticate to the Result API as viewers.

This base proof does not claim protection from the authorized human, their browser or
operating system, a malicious browser extension, an administrator, endpoint capture,
or an agent host that can observe the separately rendered viewer.

### Optional certified-deployment claim

A deployment may additionally prove that canaries remain absent from actual model
payloads and host-managed channels for a named agent host, browser, endpoint
configuration, and version set. That evidence requires host-specific tests for
screenshots, accessibility extraction, browser automation, previews, crash reports,
prompt caches, and transcript persistence. It expires when a named component changes.

## Identities and trust boundaries

| Identity | Required synthetic claims | Permitted boundary |
|---|---|---|
| Human viewer | non-empty subject; audience `snowglobe-viewer` | List, inspect, cancel, and stream only requests owned by that subject |
| Agent session | non-empty agent subject; non-empty associated human subject; audience `snowglobe-mcp` | Submit a governed request for the associated human; receive only an MCP receipt |
| Service | deployment-specific identity; never accepted as a viewer | Operate one plane according to deployment policy; no result access merely because it is a service |
| Operator | deployment-specific administrative identity | Value-free operations by default; raw result diagnostics are outside the proof |

Authentication adapters must verify claims before constructing these internal
identities. HTTP headers, request IDs, and client-supplied JSON are not claims. The
synthetic broker deliberately does not implement token verification; the production
OIDC provider, token format, and deployment store remain Phase 0 inputs.

The agent-to-human association is trusted only after control-plane authentication.
The broker copies that verified human subject into an internal request record before
an accepted receipt may be returned. The viewer authenticates independently. Its
subject must match the stored owner on every list, open, cancel, and stream action.

```text
┌──────────────┐  MCP audience   ┌─────────────┐
│ Agent host   │────────────────▶│ MCP gateway │
└──────────────┘                 └──────┬──────┘
                                       │ verified human association
                                       ▼
                                ┌─────────────┐
                                │ Broker      │
                                │ owner + TTL │
                                └──────┬──────┘
                                       │ ownership check on every action
┌──────────────┐ viewer audience       ▼
│ Human browser│────────────────▶┌─────────────┐
└──────────────┘                 │ Result API  │
                                 └──────┬──────┘
                                        │ bounded Arrow + completion proof
                                        ▼
                                 ephemeral worker
```

## Data flows and threats

| Component | Data allowed | Primary threats | Required controls for the proof |
|---|---|---|---|
| Model and agent host | SQL, purpose, requested TTL, closed receipt | Host captures tool input/output; agent tries the fixed viewer URL or observes the human viewer | No result-bearing MCP capability or URL; Result API rejects agent identity; certify host/endpoint capture paths only for the stronger claim |
| MCP gateway | Query inputs, verified agent/human association, receipt | Exceptions, logs, timing, or schemas disclose result facts | Closed schemas; fixed errors; value-free logs; final exception mapping; no resources/prompts |
| Snowflake | Not used in Milestone 1 | Credentials or database errors enter the agent environment | Keep disconnected for the synthetic proof |
| Broker | Owner, opaque request ID, status, expiry, private source handle | ID becomes bearer token; cross-user confusion; stale access | Independent viewer auth; owner check on every operation; short TTL; generic denial |
| Result API | Viewer identity and bounded Arrow stream | Wrong audience, copied ID, caching, partial publication, response/log leaks | Viewer-only audience; no-store/security headers; admission before publication; authenticated completion marker |
| Browser main thread | Value-free request list; bounded viewport/aggregate responses | Full result copy, DOM injection, URL/storage/telemetry leaks | Escaped rendering; fixed routes; no persistence/telemetry; bounded responses |
| Application worker | Provisional Arrow and in-memory DuckDB | Partial result becomes visible; state survives failure/logout/expiry | Hidden temporary table; atomic publish; terminate worker and database on every failure boundary |
| Telemetry and process output | Fixed operational categories and opaque IDs only | Values, SQL, errors, schema, counts, or sizes escape | Allowlisted fields; captured stdout/stderr/logs/traces/metrics scanned for canaries |
| Endpoint | Authorized rendered values | Screenshots, accessibility extraction, extensions, swap | Pin and test managed Chromium; document residual endpoint risk |

## Fail-closed rules

- Unknown, unauthenticated, wrong-audience, wrong-owner, cancelled, and expired
  access receives the same value-free denial at the public data boundary.
- Possession of a request ID grants no access.
- The in-process broker is test-only and is not a production durability or
  multi-process design.
- No MCP request becomes accepted until verified ownership, policy admission, and
  synthetic source association complete atomically.
- Arrow remains provisional in the worker until admission succeeds and an
  authenticated completion marker is verified. Any truncation, overflow,
  cancellation, expiry, or transport failure destroys provisional state.
- The synthetic Result API uses the terminal frame defined in
  [ADR 0005](decisions/0005-result-stream-framing.md). It omits that frame on any
  stream failure; the worker integration must reject all such incomplete streams.
- Arrow admission enforces explicitly configured row, column, scalar-cell, serialized,
  and decoded-Arrow limits as defined in
  [ADR 0006](decisions/0006-incremental-arrow-admission.md). Unsupported types and
  schema changes fail closed without exposing the reason.

## Required evidence

The base boundary harness must prove authorized visibility and canary absence across
Snowglobe MCP traffic, stdout/stderr, application logs, traces, metrics, URLs, errors,
and browser storage. Authorization tests must cover absent authentication, wrong
audience, wrong user, copied request ID, agent and service identities, revocation,
cancellation, and expiry.

A certified-deployment harness must additionally capture exact model payloads, host
history, previews, screenshots, accessibility extraction, browser automation, crash
reports, prompt caches, and transcript persistence for every named version.
