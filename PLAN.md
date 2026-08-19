# Snowglobe implementation plan

**Status:** Synthetic viewer reaches the authenticated Result API seam; public auth and MCP submission remain disconnected
**Last updated:** August 19, 2026
**Source:** [Snowflake MCP with zero-context query results](docs/architecture-proposal.md)

## 1. Outcome

Build and demonstrate a dual-channel system in which:

1. an authenticated AI agent submits one governed Snowflake read query through MCP;
2. MCP returns a constant-shape, result-independent receipt;
3. the result remains associated with the authenticated human on the server;
4. a separately authenticated SPA streams an admitted result as Arrow IPC;
5. a Web Worker loads the result into in-memory DuckDB-Wasm;
6. the human explores it with deterministic table, filter, sort, aggregate, and chart operations; and
7. seeded canary values remain absent from Snowglobe-owned agent-facing interfaces, logs, traces, URLs, errors, and browser persistence.

The MVP is a useful proof of this information boundary, not a general-purpose Snowflake IDE or a claim that software outside Snowglobe can never capture displayed data.

## 2. Assurance levels

### 2.1 Base product guarantee

Snowglobe creates no model-facing result channel. Its MCP response may indicate whether a request entered the governed path, but Snowglobe-owned agent-facing interfaces must not disclose:

- rows or cell values;
- column names or types;
- row counts or result sizes;
- query completion or whether rows exist;
- Snowflake query IDs, result tokens, or result URLs;
- database, parser, or policy details beyond a fixed reason code;
- result-dependent timing intended as status feedback; or
- charts, images, embedded resources, or downloadable artifacts.

Result bytes are released only through a separately human-authenticated and owner-authorized Result API. Agent and MCP service identities cannot authenticate as viewers. This is the default product boundary and is testable without making claims about software Snowglobe does not control.

Any later model-visible aggregate or status tool is a separately reviewed product with its own disclosure contract. It is not an extension of the base query tool.

### 2.2 Certified deployment guarantee

A deployment may additionally prove that displayed canaries do not enter model context for a named agent host, browser, endpoint configuration, and version set. That stronger claim requires host-specific capture tests for model payloads, screenshots, accessibility extraction, browser automation, host history, and similar paths. It is optional for the base product and must be rerun after relevant host or endpoint changes.

An authorized human, browser, operating system, extension, endpoint, or agent host can still capture or redisclose viewer data. If the requirement is that a model provider must never receive displayed data, the viewer must run on an endpoint outside agent-controlled browser, screenshot, accessibility, shell, and file capabilities.

## 3. Accepted architecture decisions

These are the starting constraints inherited from the architecture proposal.

| Area | Decision |
|---|---|
| Agent interface | One initial MCP tool: `submit_read_query(sql, purpose, requested_ttl)` |
| MCP output | Strict allowlisted `{status, request_id, reason_code}` receipt |
| Data delivery | Authenticated Result API streams Arrow directly to the SPA; result bytes never transit MCP |
| Viewer | Standalone deterministic SPA, not an MCP App for the MVP |
| Viewer launch | One fixed application URL exposed by static host configuration, documentation, or a bookmark; no result-specific URL or second result-bearing MCP |
| Browser analytics | In-memory DuckDB-Wasm in a dedicated Web Worker |
| Browser persistence | No IndexedDB, OPFS, service-worker cache, or automatic restoration |
| SQL | One parsed `SELECT` or `WITH … SELECT`; deny everything else |
| Data access | Approved objects/functions and a least-privileged Snowflake role |
| Snowflake configuration | Server-only `connections.toml` profile with fixed account, user, JWT authenticator, key path, database, warehouse, and role |
| Snowflake client | Official Python connector and PyArrow, adapting the minimal proven patterns from Querido |
| Backend tooling | Python 3.12+, uv, pytest, Ruff, and ty, following Querido's proven project setup |
| Backend framework | Snowglobe-owned low-level MCP handlers using the official Python protocol/Streamable HTTP transport; separately deployable Starlette MCP and Result API apps |
| SQL parser | SQLGlot Snowflake AST behind a deny-by-default Snowglobe policy and least-privileged role |
| Frontend | React, TypeScript, Vite, Apache Arrow JS, and DuckDB-Wasm owned by a dedicated application worker |
| JS workspace | npm workspaces; one viewer package does not justify additional monorepo tooling |
| Cardinality | Server-controlled outer cap of `K + 1`; never trust a model-authored `LIMIT` |
| Admission | Enforce compute, row, column, cell, Arrow-byte, and memory budgets before publishing a result |
| Result identity | Opaque request ID is a correlator, not a secret or Snowflake query ID |
| Oversized data | Reject or deliberately server-page; never silently truncate or spill into browser storage |
| UI conversion | Bounded Arrow viewport reads; no full-table JSON, JSONL, `toArray()`, or row-object store |
| Initial exclusions | Export, sharing, persistence, arbitrary uploads, external extensions, third-party telemetry, and model analysis of rows |

## 4. Decisions and deployment inputs

Foundation technology decisions are recorded. Phase 0 remains open until the environment-specific policy and deployment inputs below are resolved; they do not block the synthetic proof.

| Decision | Proposed MVP default | Why it matters |
|---|---|---|
| Base guarantee | No result-derived information through Snowglobe-owned agent-facing interfaces | Determines the MCP contract and base test oracle without overclaiming control of the endpoint |
| Stronger assurance | Optional certification of one explicit host/browser/endpoint version set | Required only for a deployment claim about actual model context assembly or screen capture |
| Allowed data | Synthetic data, then explicitly approved secure views | Prevents accidental broad access during development |
| Query flexibility | Parsed read-only SQL over an object allowlist | Templates are safer; free-form SQL may still be a validated requirement |
| Human authentication | Enterprise OIDC with audience-bound viewer sessions | Must be different from agent/service authorization |
| Snowflake identity | Configured key-pair service identity initially; evaluate delegated per-user identity before production | The provided connection contract is service-oriented; the gateway must preserve human identity separately |
| Result lifecycle | Short-lived persisted Snowflake result or server-held cursor | Avoids creating an additional unmanaged data copy |
| Default TTL | 15 minutes for the proof; benchmark before production | Must be short without making ordinary use impractical |
| Viewer library | Start with a minimal accessible viewport; prototype Mosaic/vgplot and compare a specialized grid before Milestone 3 | Choice must be driven by memory, accessibility, and viewport behavior |
| Deployment boundary | Distinct MCP and Result API auth audiences; separate network deployment when the threat model requires it | Logical identity separation is mandatory; duplicating code or processes is not |
| Agent hosts | No host prerequisite for the base claim; certify explicit versions for the stronger claim | The server cannot control host logging, endpoint capture, or context assembly |
| Export | Disabled | Export creates a separate governance and retention product |
| Oversized results | Reject and ask the human to narrow | Server paging can be added only for a demonstrated use case |
| Supported browsers | Current managed Chromium initially | Memory behavior and security controls need a testable endpoint baseline |

Recorded in the [architecture decision log](docs/decisions/README.md): runtime, Snowglobe-owned low-level MCP surface, transport, ASGI boundary, parser candidate, frontend, worker ownership, workspace tooling, configuration vocabulary, a test-only initial broker strategy, and the split between the base product boundary and optional endpoint certification.

The following are required before a production pilot, but intentionally do not block the synthetic proof:

1. Does the deployment need the stronger certified model-context claim, and if so which agent-host, browser, and endpoint versions are in scope?
2. Which Snowflake databases, schemas, secure views, and data classifications may be queried?
3. Is arbitrary read SQL essential, or can the initial product use query templates and approved views?
4. Which OIDC provider will authenticate humans, and is a shared JWT Snowflake service identity acceptable for the intended data policies?
5. What retention, audit, incident-response, and regulatory requirements apply?
6. What representative result sizes, schemas, browsers, and endpoint memory tiers should benchmarks cover?
7. Is polished spreadsheet interaction more important than the fastest integrated chart/table prototype? Use measured prototypes to inform this product preference.

## 5. Repository shape

The initial scaffold keeps one Python distribution while exposing separately runnable control- and data-plane modules. Split deployment artifacts when deployment topology requires it; do not duplicate internal contracts merely to create cosmetic directories.

```text
snowglobe/
├── apps/
│   └── viewer/            # SPA and dedicated DuckDB-Wasm worker
├── src/snowglobe/
│   ├── mcp_gateway.py     # model-facing control-plane ASGI app
│   ├── result_api.py      # human-facing data-plane ASGI app
│   ├── arrow_stream.py    # incremental Arrow admission and IPC serialization
│   ├── broker.py          # test-only in-process ownership broker
│   ├── contracts.py       # strict model-visible receipt
│   ├── configuration.py   # strict connections.toml loader
│   └── private_key.py     # RSA key conversion
├── tests/
│   └── ...                # unit tests; add boundary suites with Milestone 1
├── docs/
│   ├── README.md
│   ├── threat-model.md    # synthetic identities, flows, and test obligations
│   ├── architecture-proposal.md
│   └── decisions/         # architecture decision records
├── .agents/
│   ├── setup              # install orb toolchains and locked dependencies
│   └── resume             # fast orb toolchain availability check
├── assets/
└── AGENTS.md              # durable agent guardrails
```

The deployable apps intentionally remain disconnected from the test-only broker: there is no result-bearing route, and every MCP submission returns `SERVICE_UNAVAILABLE`. “Accepted” becomes possible only after authentication adapters, policy admission, broker submission, and failure-atomic result streaming are connected together.

### 5.1 Querido reuse boundary

The detailed audit is in [docs/querido-reference.md](docs/querido-reference.md), pinned to Querido commit `eb6879e80a09acd0a4c090c42801d68f7fc101d9`.

Build Snowglobe-owned modules for only these responsibilities:

```text
configuration.py   strict TOML version/profile/field validation
private_key.py     PEM/DER RSA → PKCS#8 DER conversion
snowflake.py       explicit driver arguments and connection lifecycle
execution.py       one request → one cursor, incremental Arrow, cancellation
errors.py          stable internal categories and boundary-safe serialization
```

Adapt from Querido:

- standard-library TOML loading and schema-version rejection;
- `~` expansion for server-local key paths;
- PEM-first/DER-fallback private-key conversion;
- explicit cursor ownership with `finally` cleanup;
- context-managed connection closure;
- typed internal error categories;
- mocked Snowflake/Arrow test seams; and
- hostile SQL examples as parser-policy fixtures.

Do not adapt:

- generic connector/factory/CLI machinery;
- flexible `**config` forwarding;
- interactive credential caching;
- connector-wide cancellation;
- `list(fetch_arrow_batches())`, table concatenation, lowercasing, `to_pylist`, or `fetchall` fallback;
- raw driver messages, SQL echoing, account logging, or CLI recovery hints;
- Querido's first-keyword SQL scanner as the policy engine; or
- its subprocess MCP proposal and model-visible query envelopes.

Querido has no implementation to reuse for query tags, statement/network timeouts, persisted-result retrieval, `RESULT_SCAN`, strict config/key permission checks, Arrow IPC backpressure, or cross-user result authorization. These remain explicit Snowglobe work.

## 6. Delivery milestones

### Milestone 0 — policy, threat model, and technical spikes

**Goal:** settle the claim and show that the key dependencies can support it before building the product.

Tasks:

- [ ] Answer the Phase 0 questions in section 4.
- [x] Write a data-flow threat model covering model, host, MCP gateway, Snowflake, broker, Result API, browser, telemetry, and endpoint.
- [ ] For a certified deployment, inventory every agent-accessible shell, file, browser, HTTP, screenshot, accessibility, and MCP path in the proposed host.
- [x] Define human, agent, operator, and service identities plus trust boundaries.
- [ ] Define result classification, retention, deletion, audit, and incident-response policy.
- [x] Adapt Querido's narrow TOML loading and JWT/private-key conversion patterns.
- [ ] Implement Snowglobe-owned Snowflake connection, cursor lifecycle, and incremental Arrow retrieval.
- [x] Pin the Querido reuse baseline by commit and preserve attribution for any substantially copied fragment.
- [x] Build a strict read-only config loader: version check, exact root/profile shape, required/unknown fields, server-selected profile, and fail-closed missing-file behavior.
- [ ] Define config/key file permission policy for local hosts and mounted container secrets; Querido checks neither on read.
- [x] Extract and test RSA private-key loading with generated PEM/DER fixtures; cover malformed, encrypted-without-secret, missing, and unsupported keys without leaking paths or cryptography errors.
- [ ] Construct Snowflake driver kwargs from an explicit allowlist; never forward a configuration dictionary wholesale.
- [ ] Exclude Querido's interactive credential-cache and MFA-token flags from the JWT service connection.
- [ ] Spike persisted-result and incremental Arrow batch behavior without exposing `connections.toml`, private-key bytes, credentials, query IDs, or tokens to the agent environment.
- [ ] Verify the connector can consume batches incrementally; do not copy Querido's list-and-concatenate or Arrow-to-dictionary result materialization.
- [ ] Spike server-owned Snowflake session parameters: opaque query tag, statement/queue timeout, detached-query behavior, login/network timeout, and application identifier.
- [ ] Decide connection ownership and concurrency model; cancellation and result access must be request-scoped rather than connector-global.
- [ ] Evaluate Snowflake SQL parsers against the required grammar and AST rewrite; reject regex-only approaches.
- [ ] Port Querido's quote/comment/CTE/out-of-band-write SQL cases as seed fixtures, then add Snowflake-specific function, stage, scripting, and nested-query attacks.
- [ ] Verify that `LIMIT K + 1` rewriting preserves top-level ordering and existing limit semantics for accepted queries.
- [x] Spike Arrow streaming through backpressure into a Web Worker and provisional DuckDB table.
- [ ] Benchmark Mosaic/vgplot and Glide against the same synthetic Arrow viewport contract.
- [x] Record foundation runtime, low-level MCP, parser, viewer, configuration, deployment-boundary, assurance-level, and viewer-launch choices as decision records.
- [ ] Record environment-specific authentication, identity, retention, and deployment choices when inputs are known.

Exit criteria:

- The base product promise and stronger certified claim are separately testable.
- A parser can prove and rewrite the allowed SQL subset.
- A connector path can produce bounded Arrow without row logging or full row-object conversion.
- The chosen browser path loads provisionally, publishes atomically, and destroys state on failure.
- Every production dependency has a named owner and rationale.

### Milestone 1 — synthetic vertical boundary proof

**Goal:** prove the complete control/data split with no Snowflake production connectivity.

#### MCP control plane

- [x] Implement the fail-closed low-level `submit_read_query` shell with strict input and output schemas.
- [x] Generate 20–32 character random opaque request IDs with no embedded identity or query data.
- [x] Return only `accepted`/`rejected` and fixed reason codes.
- [x] Map all unexpected exceptions to `SERVICE_UNAVAILABLE` at the final serialization boundary.
- [x] Prohibit MCP resources, prompts, notifications, embedded content, and result-reading tools.
- [x] Verify the exact contract through the real Streamable HTTP transport.
- [x] Capture and scan stdout/stderr for an unexpected canary-bearing MCP exception.
- [ ] Capture and scan stdout/stderr around the eventual executor and driver.

#### Synthetic broker and Result API

- [x] Associate requests with verified internal human claims, status, expiry, and a synthetic Arrow source; public authentication remains disconnected.
- [x] Use separate agent and viewer auth audiences.
- [x] Authorize list, open, cancel, and stream operations on every request.
- [x] Refuse possession-only access by request ID.
- [x] Stream byte-bounded synthetic Arrow IPC chunks with `Cache-Control: no-store` and security headers.
- [x] Count actual rows, serialized/decoded bytes, columns, and maximum scalar cell size while streaming; reject unsupported nested types.
- [x] Emit a terminal completion frame on the authenticated Result API response; omit it on cancellation, truncation, expiry, source failure, or byte overflow.
- [ ] Keep values out of normal logs, metrics labels, traces, exceptions, URLs, and response metadata.

#### Viewer

- [ ] Authenticate the human through a deployment-selected identity provider.
- [x] List only the authenticated viewer's recent requests at a fixed application URL.
- [x] Stream Arrow through a `ReadableStream` directly to a dedicated worker with backpressure.
- [x] Ingest into a hidden temporary in-memory DuckDB table.
- [x] Publish the table only after a valid completion marker.
- [ ] Terminate the worker and destroy the database on error, overflow, expiry, logout, or close.
- [x] Render escaped cells from one row- and byte-bounded DuckDB viewport.
- [ ] Virtualize the table for larger viewport windows.
- [ ] Implement deterministic DuckDB-backed pagination, projection, sorting, and filtering.
- [ ] Add one bounded aggregate chart without sending raw rows to the UI thread.
- [ ] Enforce a byte-bounded Arrow viewport cache and cancel stale scroll requests.
- [ ] Disable persistence, external data readers, unapproved extensions, export, copy-all, and third-party scripts.

#### Boundary harness

- [ ] Seed unique canaries in cells, column names, malformed values, driver errors, Unicode, binary values, and oversized values.
- [ ] Capture Snowglobe MCP traffic, process output, logs, traces, metrics, URLs, browser storage, and errors.
- [ ] Assert that canaries are visible in the authorized viewer and absent from every Snowglobe-owned agent-facing or persistence channel.
- [ ] Prove that unauthenticated, wrong-user, copied-URL, expired, agent, and service identities cannot retrieve data.
- [ ] For a certified deployment, additionally capture model requests, host history, previews, screenshots, accessibility extraction, browser automation, and crash reporting.

Exit criteria:

- The complete synthetic user journey works.
- Base leak and authorization tests pass independently of any host-specific certification.
- A partial or oversized stream never becomes visible.
- No code path materializes the full dataset as JavaScript rows.

### Milestone 2 — governed Snowflake integration

**Goal:** replace the synthetic executor with a least-privileged Snowflake path while preserving the proven contracts.

#### SQL policy

- [ ] Accept exactly one parsed `SELECT` or `WITH … SELECT` statement.
- [ ] Deny DDL, DML, `CALL`, scripting, dynamic SQL, stages, file transfer, external functions, network-capable functions, and unapproved UDFs.
- [ ] Allowlist databases, schemas, secure views, functions, and warehouses.
- [ ] Deny user-selected roles and warehouses.
- [ ] Reject unbounded wildcards against governed large objects.
- [ ] Apply a semantics-preserving top-level `K + 1` cap.
- [ ] Property-test comments, quoted identifiers, literals, nested CTEs, set operations, Unicode, and multi-statement attacks.
- [ ] Store only the approved normalized audit representation; define handling for sensitive SQL literals.

#### Execution and broker

- [ ] Load one named profile from the server-only `connections.toml` contract documented in `docs/configuration.md`.
- [ ] Validate required and unknown fields; require `authenticator = "SNOWFLAKE_JWT"` in the initial implementation.
- [ ] Read PEM or DER RSA private-key material from `private_key_path`, convert it in memory to unencrypted PKCS#8 DER for the connector, and never log or serialize it.
- [ ] Pass Snowglobe's `database` field directly to the connector's `database` parameter.
- [ ] Pass configured account, user, database, warehouse, and role to the connector; never accept role or warehouse overrides from MCP input.
- [ ] Pass no interactive credential-cache/MFA settings; add only reviewed server-owned session parameters.
- [ ] Preserve Arrow field names and types on the human data path; do not copy Querido's lowercase-column normalization.
- [ ] Provision a dedicated smallest-approved warehouse, role, resource monitor, and network policy.
- [ ] Apply statement, queued-query, concurrency, per-user, and tenant limits.
- [ ] Bind every request to the authenticated human in Snowglobe audit records and query tags; document the shared Snowflake identity and evaluate delegated identity before production.
- [ ] Use opaque query tags containing request/application IDs only.
- [ ] Keep Snowflake query IDs, credentials, and result tokens server-side.
- [ ] Close or cancel work immediately when a runtime or result budget is crossed.
- [ ] Inspect completed-result metadata before browser release.
- [ ] Validate actual Arrow batches against row, byte, cell, column, and memory limits.
- [ ] Process `fetch_arrow_batches()` incrementally with backpressure; never call `list(...)`, concatenate the full result server-side, or convert it to Python dictionaries.
- [ ] Treat unavailable Arrow retrieval as a human-path failure; never fall back to `fetchall()`.
- [ ] Preserve a valid schema/completion contract for an empty result.
- [ ] Register each active cursor by request/owner and make close/cancel idempotent; never cancel all cursors on a shared connector.
- [ ] Expire result associations and verify that retrieval fails after expiry.

Exit criteria:

- The Snowflake role cannot mutate objects, escalate role/warehouse, access stages, call dangerous functions, or query unapproved objects.
- Expensive low-cardinality and oversized high-cardinality canary queries are stopped by independent controls.
- Snowflake-backed canaries satisfy the same boundary suite as synthetic data.
- No additional raw export or result copy is created by default.

### Milestone 3 — browser analysis hardening

**Goal:** make local exploration useful and bounded without weakening the data boundary.

- [ ] Finalize the grid choice using measured scroll latency, memory, accessibility, keyboard navigation, theming, and security behavior.
- [ ] Normalize filters, sorts, and projections into parameterized local SQL.
- [ ] Query only the visible row/column window plus modest overscan.
- [ ] Keep the display cache columnar, byte-bounded, and least-recently-used.
- [ ] Return chart aggregates sized to marks/pixels rather than source cardinality.
- [ ] Enforce independent DuckDB table, query working-memory, Arrow, and display-cache budgets.
- [ ] Benchmark realistic strings, nulls, wide JSON-like cells, sorting, aggregation, and rapid scrolling.
- [ ] Add content-security, HTML escaping, referrer, frame, browser-cache, and indexing tests.
- [ ] Confirm values never enter route state, titles, notifications, clipboard defaults, or telemetry.
- [ ] Test logout, tab close, session revocation, result expiry, worker failure, and network interruption.

Exit criteria:

- Supported endpoint tiers remain within defined peak-memory budgets.
- Sorting/filtering uses DuckDB and never builds a full JavaScript array.
- Grid scrolling stays within the display-cache budget.
- Security headers and browser non-persistence tests pass.

### Milestone 4 — deployment hardening and optional host certification

**Goal:** deploy a reviewable pilot and make only the assurance claims supported by evidence.

- [ ] Deploy MCP and Result API with distinct network routes and auth audiences.
- [ ] Ensure coding environments have no Snowflake credentials or access to result storage/API.
- [ ] Restrict Result API CORS, CSP `connect-src`, and service identity access.
- [ ] Add value-free operational metrics and allowlisted structured logs.
- [ ] Add alerts for policy rejection spikes, cross-user attempts, unusual volume, and retention failures.
- [ ] Run authorization review, penetration test, and retention/deletion verification.
- [ ] Write operator runbooks for cancellation, revocation, incident response, key rotation, and host upgrades.
- [ ] If the stronger claim is required, capture exact model payloads and host persistence after MCP execution.
- [ ] If the stronger claim is required, test screenshots, accessibility extraction, previews, browser automation, crash reports, and prompt caches.
- [ ] If the stronger claim is required, pin and certify exact agent-host, server, browser, and endpoint versions.

Exit criteria:

- Security, privacy, and Snowflake owners approve the scoped base acceptance statement.
- A pilot user can complete the journey under production-like identity and network controls.
- Canary evidence is retained without retaining canary-bearing rows in ordinary telemetry.
- Any stronger host-specific claim names the tested versions and expires when they change; untested hosts remain outside that claim unless real host attestation can make them fail closed.

### Milestone 5 — controlled usability, only after the boundary is proven

Candidate features, each requiring its own requirements and security review:

- [ ] richer coordinated charts;
- [ ] saved viewer configuration containing identifiers/rules but no cell values;
- [ ] authorized server-paged mode;
- [ ] audited export with classification, rate, retention, and deletion controls;
- [ ] explicit human-approved disclosure of a bounded viewer selection to an agent;
- [ ] reviewed metadata/catalog access;
- [ ] narrow model-visible aggregate or `PASS`/`FAIL`/`SUPPRESSED` tools;
- [ ] deterministic host-side “Open Snowglobe” action backed only by the static viewer URL; and
- [ ] MCP App evaluation only for hosts that prove app-only data separation.

### Backlog idea — controlled viewer-to-agent disclosure

After proving the base product boundary, evaluate an explicit workflow in which a human uses DuckDB-Wasm to project columns, filter rows, sort, and apply a small row limit, then deliberately discloses that exact subset to an agent. This is a **separate disclosure product**, not “sanitization” merely because fewer cells are selected, and it changes the guarantee for the disclosed subset: those values may enter model input, host history, logs, prompt caches, and provider retention.

Prototype the least-integrated option first:

1. **Copy for paste:** render a bounded selection as escaped Markdown, CSV, or JSON; show an exact preview and estimated size/token count; require a human click to copy; then let the human paste it into the conversation. Nothing reaches the agent until the paste.
2. **Audited download/export:** create a short-lived local artifact only if users need file-shaped context. This adds endpoint storage, agent file-access, retention, deletion, and classification concerns, so it should not be the default.
3. **Direct agent handoff:** add a host-specific, human-initiated integration that sends the approved payload to one certified conversation. Do not route it through the base query receipt or add a generic model-callable `read_result` tool. Direct handoff requires proof that the selected host displays the exact payload for confirmation and does not silently enrich it with undisclosed viewer state.

Every option must:

- start from an explicit human selection or saved deterministic DuckDB query, never the full result by default;
- show the exact columns, rows, formatting, and bytes that will leave the viewer;
- enforce independent row, column, cell, byte, and token limits;
- reapply an egress policy for classifications, masking, minimum groups, prohibited columns, and dangerous content rather than trusting projection/filtering alone;
- treat cell text as untrusted data, escaping format delimiters and clearly separating it from agent instructions to reduce prompt-injection risk;
- require a fresh confirmation naming the destination agent/conversation and the resulting disclosure consequences;
- avoid values in URLs, telemetry, audit labels, notifications, and ordinary logs;
- record value-free provenance such as request ID, user, destination, selected column identifiers, filter/query fingerprint, counts, time, policy version, and approval outcome;
- prevent background synchronization, automatic retries to another destination, and reuse after result/session expiry; and
- have canary tests proving that only the previewed payload—not hidden rows, omitted columns, worker state, or result metadata—reaches the certified agent context.

Open product questions for this backlog item:

- Is manual copy/paste sufficient, or does direct handoff remove enough friction to justify host-specific security work?
- Which formats best preserve types while remaining understandable and resistant to instruction/data confusion?
- Must disclosure be limited to already masked values, or can a separate policy approve otherwise prohibited source classifications?
- Should the disclosed payload include a human-readable provenance header, and which identifiers are safe for model context?
- Can a user revoke or expire a direct handoff before the host submits its next model request?

## 7. Contract sketch

Initial model-visible response:

```json
{
  "status": "accepted",
  "request_id": "01JABCDEFGHJKMNPQRSTVWXYZ",
  "reason_code": "NONE"
}
```

Rules:

- `additionalProperties` is false at the schema and serialization boundaries.
- The low-level server handwrites the schemas, validates arguments itself, and constructs both MCP result channels explicitly.
- `status` is exactly `accepted` or `rejected`.
- `request_id` is 20–32 URL-safe ASCII characters matching `^[A-Za-z0-9_-]{20,32}$`.
- `reason_code` is exactly `NONE`, `INVALID_REQUEST`, `POLICY_REJECTED`, or `SERVICE_UNAVAILABLE`.
- Accepted means only that the request entered the governed path.
- The receipt does not reveal completion, result existence, result size, or database error detail.
- Response size is capped and every emitted byte is schema validated.
- Text content is compact JSON representing exactly the same fields as structured content.
- Unknown tool names receive one fixed, non-reflective tool error with no structured content.
- Snowglobe does not attach application `_meta`; transport-added server identity is fixed and must remain result-independent.
- Initialization advertises tools only, with no resources or prompts capability.

The Result API contract is intentionally not placed in MCP metadata or responses. It will be versioned separately and require an audience-bound human session.

## 8. Test strategy

### Test layers

| Layer | Primary evidence |
|---|---|
| Unit | schema closure, reason-code mapping, ID generation, policy rules, byte counters |
| Config/key | strict TOML shape, profile selection, PEM/DER RSA conversion, file policy, secret-safe failures |
| Property/fuzz | SQL bypass attempts, hostile values, Unicode, large cells, serialization leaks |
| Integration | explicit driver kwargs, connector lifecycle, incremental Arrow backpressure, provisional publish, expiry, request-scoped cancellation |
| Authorization | cross-user, wrong audience, unauthenticated, revoked, expired, service identity |
| Browser | escaping, CSP, no storage/cache, worker destruction, viewport-only conversion |
| Performance | peak memory, ingestion rate, scroll latency, sort/aggregate working space |
| Base end-to-end boundary | canary visible to human and absent from Snowglobe-owned agent-facing and persistence channels |
| Optional host certification | exact model payload, transcript, traces, previews, screenshots, accessibility paths |

### Required adversarial fixtures

- a normal unique canary cell;
- a canary used as a column name;
- a canary embedded in a database error;
- HTML/script and prompt-injection-looking text;
- Unicode, nulls, binary values, and invalid encodings;
- one cell over the cell limit;
- narrow rows over the row cap;
- wide rows under the row cap but over the byte/memory cap;
- a stream crossing a limit only in its final batch;
- an expensive query returning few rows;
- an unbounded wildcard over a large governed object;
- cancellation, disconnect, token revocation, and expiry during ingestion; and
- simultaneous requests belonging to different users.

Querido-derived regression fixtures additionally cover CTE-prefixed writes, multiple statements, quote/comment confusion, unterminated input, `COPY`, `PUT`, `CALL`, `EXECUTE IMMEDIATE`, external state operations, and dangerous `EXPLAIN` targets. Snowglobe's AST policy must classify them without relying on Querido's first-keyword scanner.

## 9. Initial non-goals

- Letting the model inspect or summarize arbitrary results.
- Returning schema, counts, previews, errors, or signed links through MCP.
- General Snowflake administration, DDL, DML, procedures, stages, or file transfer.
- A generic SQL IDE, notebook, or BI replacement.
- Durable browser datasets or offline use.
- Public links, result sharing, CSV/Parquet download, or copy-all.
- Supporting every browser, agent host, Snowflake identity pattern, or data domain in the first release.
- Claiming that an authorized human, browser extension, OS, administrator, or future host can never disclose data.

## 10. Definitions of done

### Base product proof

The base proof is done when evidence supports this statement:

> Snowglobe's model-facing interfaces emit only a schema-constrained, result-independent receipt. Query-result canaries are visible to the authorized human in the governed viewer and absent from Snowglobe-owned agent-facing interfaces, logs, traces, URLs, errors, and browser persistence. Viewer authorization is independent, and agent or service identities cannot retrieve results.

This statement must be rerun after changes to MCP transport, authentication, connector, result handling, viewer, telemetry, browser policy, or deployment topology.

### Optional certified deployment proof

A deployment that also captures the exact model payload and host-managed channels may make this additional statement:

> For the named agent-host, server, browser, endpoint configuration, and versions, seeded viewer canaries are absent from all captured model inputs and host-managed agent-visible channels.

This stronger statement must be rerun after changes to any named component.

## 11. Immediate next iteration

Completed in the current iteration:

1. Reviewed the complete trust model, implementation, and current MCP/MCP Apps behavior.
2. Separated Snowglobe's testable base product boundary from optional host/browser/endpoint certification.
3. Confirmed that a second model-facing MCP does not isolate result data and selected one fixed standalone viewer URL/action instead.
4. Retained incremental admission and failure-atomic browser publication as correctness, resource, and lifecycle controls rather than presenting them as host-isolation evidence.
5. Added final MCP exception sanitization, stdout/stderr canary coverage, and a real Streamable HTTP client round trip.
6. Connected the fixed viewer URL to the credential-bearing Result API list and stream routes, retained stream backpressure through the dedicated worker, and rendered one 50-row/256-KiB DuckDB viewport only after failure-atomic publication.

Next:

1. Select and implement the public human authentication adapter; the deployable Result API remains deny-all until that deployment input is known.
2. Connect synthetic MCP acceptance only after verified ownership, policy admission, and broker submission succeed together.
3. Build the base leak/authorization harness before connecting any sensitive Snowflake account.
4. Time-box SQLGlot corpus/`K + 1` and Snowflake incremental Arrow spikes without joining them to the accepted path until their contracts hold.
