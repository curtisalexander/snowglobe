# Snowflake MCP with zero-context query results

## How a coding agent can execute useful Snowflake queries without giving result values to the LLM

**Design date:** August 18, 2026  
**Status:** Architecture proposal; requires security, privacy, Snowflake, and agent-platform review

---

## Executive summary

Yes, this can be designed—but the MCP server is only one part of the boundary.

The safest pattern is to split the system into two paths:

1. **Agent control path:** the coding agent submits SQL through an MCP tool. The tool returns only a fixed, non-sensitive receipt.
2. **Human data path:** a separately authenticated, deterministic web viewer obtains Arrow data from a governed result service, loads it into DuckDB-Wasm, and renders or queries it directly in the user's browser.

```diagram
                         CONTROL PATH — no result values
┌──────────────┐   tool call   ┌─────────────┐   validated request   ┌───────────┐
│ Coding agent │──────────────▶│ MCP gateway │──────────────────────▶│ Snowflake │
│ + LLM        │◀──────────────│             │◀──────────────────────│           │
└──────────────┘ fixed receipt └──────┬──────┘ rows stay server-side └───────────┘
                                      │
                                      │ opaque execution association
                                      ▼
                               ┌──────────────┐
                               │ Result API   │
                               │ + broker     │
                               └──────┬───────┘
                                      │ authenticated Arrow stream
                         DATA PATH — no agent or MCP transit
                                      ▼
                               ┌──────────────┐
                               │ SPA          │
                               │ DuckDB-Wasm  │
                               └──────┬───────┘
                                      ▼
                                authorized human
```

The viewer is not optional if people need to inspect arbitrary rows while the model must not see them. A strong implementation is a tightly controlled single-page application that streams Apache Arrow into an in-browser DuckDB-Wasm database. The human can then filter, sort, aggregate, join, chart, and issue subsequent SQL against the returned dataset without another Snowflake call and without involving the model. What matters is that its data API, authentication, logs, exports, browser storage, and behavior are outside the agent's tool and context paths.

The strongest initial design is:

- a small remote MCP gateway with one read-only query tool;
- per-user Snowflake identity where practical;
- a SQL parser and policy engine, backed by a genuinely least-privileged Snowflake role;
- no row values, previews, schemas, counts, Snowflake errors, or result URLs in MCP responses;
- an authenticated SPA reached through a fixed application URL or a human-only host UI action;
- Arrow streaming from a server-side Snowflake cursor or persisted query result directly to DuckDB-Wasm, with short expiration and bounded browser memory;
- source-level masking and row-access policies;
- explicit tests that scan every agent-visible channel for seeded canary values.

This architecture can make **query result values** absent from model context by construction. It cannot honestly promise that the model learns nothing about the data if the MCP response includes counts, schema, detailed errors, timing, or policy-approved aggregates. Those are result-derived information too. The contract must say which claim is intended.

---

# 1. Start with a precise guarantee

“Never inject results into context” can mean two different things.

## Guarantee A: no row values

Raw cells and rendered rows never enter the model context. The tool may return approved metadata such as row count, column names, or aggregate statistics.

This is useful, but metadata can still disclose sensitive facts. A count of one, a rare category, a revealing column name, or a detailed conversion error may identify a person or value.

## Guarantee B: no result-derived information

The MCP response does not vary based on result contents. It returns only a generic acceptance receipt, for example:

```json
{
  "status": "accepted",
  "request_id": "01J..."
}
```

No row count, schema, sample, aggregate, detailed database error, result-bearing image, presigned URL, or execution timing is returned to the agent. Query completion and error detail appear only in the human viewer.

**Recommendation:** make Guarantee B the base mode. Add separately reviewed tools for approved aggregates when the business needs model-assisted interpretation. Do not quietly weaken “zero context” by calling counts or schema “just metadata.”

The remaining document uses **zero-context results** to mean Guarantee B: result values and result-derived details do not cross into the agent channel.

---

# 2. Why MCP alone is not the display layer

The core MCP tool flow sends a tool result from the server to the client and then lets the client provide it to the model. MCP tool results may contain text, structured content, images, resource links, or embedded resources. Therefore:

- returning rows as text or JSON exposes them;
- returning a chart exposes its plotted values, even if the table is hidden;
- returning an embedded resource exposes it;
- returning a resource link is safe only if the agent cannot dereference it through MCP, a browser tool, `curl`, a file tool, or another route;
- marking content with an audience annotation is not a sufficient security boundary unless the exact host is proven to enforce it outside model context.

An MCP server controls what it returns, but it does **not** control everything the host logs, renders, or sends to the model. A credible guarantee therefore requires either:

1. a separately governed viewer that never receives rows through MCP; or
2. a custom agent host with a formally separated human-only output channel.

For a first implementation, the separate viewer is easier to reason about and test.

## Why a second MCP does not create the data path

It is tempting to use one MCP server to execute the Snowflake query and a second MCP server to fetch Arrow and load the viewer. Separation of responsibilities is useful, but merely adding another MCP server does not create information-flow separation. If the second server returns Arrow bytes, rows, an embedded resource, or a result-bearing URL through a normal MCP tool result, those values still pass through the agent host and may enter model context, transcripts, previews, or logs.

The safe division is:

- **Query MCP:** model-facing control plane; accepts SQL and returns only a receipt.
- **Result API:** human-facing data plane; authenticates the viewer and streams Arrow directly to it.
- **SPA with DuckDB-Wasm:** deterministic local analysis and display plane.

The model may submit a query and request that the host open the viewer. It must not fetch the bytes that populate the viewer.

If a second MCP is retained for organizational reasons, the SPA—not the model—must call it over a host-enforced app-only channel whose responses are excluded from model messages, transcripts, traces, previews, screenshots, and accessibility extraction. That requires certification of the exact host. Once those requirements exist, a conventional authenticated HTTP result API is usually simpler and easier to audit than MCP.

## What about MCP Apps?

MCP Apps are useful for interactive dashboards, but they are not automatically a private user-only data channel. The current MCP Apps documentation shows the server's tool result traveling through the agent/host and then being pushed to the app. Apps can also send model-context updates. Sandboxed iframes protect the host from app code; they do not, by themselves, prove that sensitive app data bypassed the model and transcript.

An MCP App could be used only if the chosen host supports and enforces all of the following:

- app-only tool results that are never added to model messages, transcripts, traces, or model-visible tool history;
- no automatic serialization of app state, screenshots, accessibility trees, or previews into context;
- `updateModelContext`, messaging, and model-visible tool calls disabled for result data;
- a separate authorization context for app data requests;
- auditable information-flow tests for that exact host version.

Without those guarantees, use a standalone viewer. “Rendered inside the chat” is a convenience feature, not proof of data separation.

---

# 3. Recommended architecture

## 3.1 Coding agent and MCP client

The agent can:

- draft and revise SQL;
- submit a query request;
- receive a generic accepted/rejected receipt;
- explain how the user can open the approved viewer;
- continue working on code that does not require seeing the values.

The agent cannot:

- use a general Snowflake CLI or direct connector;
- retrieve the result through another MCP resource;
- read viewer storage, browser caches, downloads, or temporary files;
- call the viewer data API;
- receive screenshots or copied text from the viewer automatically.

The coding environment should not contain Snowflake credentials. The MCP gateway should run remotely, or in an isolated local process whose credentials and result files are inaccessible to shell and file tools.

## 3.2 MCP gateway

Expose a deliberately small tool surface, ideally one tool to begin:

```text
submit_read_query(sql, purpose, requested_ttl)
    -> { status, request_id }
```

The gateway:

1. authenticates the human and binds the MCP session to that identity;
2. validates the request and SQL policy;
3. records an audit event without recording returned values;
4. executes under the correct Snowflake identity and role;
5. associates the server-side result with the user and request;
6. returns a constant-shape receipt.

Do not expose `get_results`, `preview_rows`, `read_resource`, `download_csv`, or a generic “run arbitrary program” tool on the same MCP server.

## 3.3 Query policy engine

Do not rely on a prompt or a regular expression to make SQL read-only. Parse the SQL into an abstract syntax tree and allow only a narrow grammar. The first version should permit a single `SELECT` or `WITH … SELECT` statement and reject everything else.

Policy checks should include:

- exactly one statement;
- approved databases, schemas, secure views, functions, and warehouses;
- no DDL or DML;
- no `CALL`, anonymous procedure, scripting block, dynamic SQL, stage command, file transfer, external function, network-capable function, or unapproved UDF;
- no user-selected role or warehouse;
- bounded statement timeout and warehouse size;
- bounded rows, bytes, and concurrency;
- optional estimated-cost approval before execution;
- normalized SQL stored for audit, with care because SQL literals themselves may contain sensitive data.

The parser is an application control. The Snowflake role is the security backstop: it should have only the privileges needed to query approved views and use a dedicated warehouse. If parser policy fails, the role should still be unable to write data, create objects, call dangerous functions, access stages, or administer the account.

## 3.4 Snowflake execution identity

Prefer delegated or per-user identity so Snowflake policies and audit records reflect the requesting person. This enables row-access and masking policy decisions based on the actual user or role.

If a shared service identity is unavoidable:

- give it a dedicated, minimal role;
- perform strong authorization in the gateway;
- bind every request and result to the authenticated human;
- accept that Snowflake will primarily see the service identity and preserve the human identity in a non-sensitive query tag and application audit trail;
- prohibit users from choosing or escalating the Snowflake role.

Apply Snowflake controls independently of the agent design:

- secure views where a narrower data product is appropriate;
- row access policies;
- masking and tag-based masking policies;
- object and column classification;
- network policies and strong authentication;
- a dedicated warehouse, resource monitor, statement timeout, and concurrency limits;
- query tags containing opaque request and application identifiers—not prompts, customer identifiers, or SQL values;
- Access History and Query History review.

## 3.5 Result broker

The result broker owns the association between:

- the opaque application `request_id`;
- authenticated user and authorization context;
- Snowflake query ID or server-side cursor;
- status and expiration;
- viewer permissions and audit history.

The broker should not place rows in its normal application logs. Depending on scale and retention needs, it can use one of three strategies:

| Strategy | Advantages | Risks and limits |
|---|---|---|
| Stream an active server-side cursor | Least additional persistence; straightforward MVP | Long queries and browser sessions require careful lifecycle handling |
| Stream or page a Snowflake persisted result by server-held query identity | No separate raw export; Snowflake persists successful query results for 24 hours | Retrieval authorization and connector token lifecycle must be handled server-side; retention is not fully application-controlled |
| Write an encrypted governed artifact | Supports large results, exports, and longer review | Creates another sensitive copy requiring classification, access control, retention, deletion, and audit |

**Recommendation:** start with short-lived Snowflake persisted results or a server-side cursor. Do not create CSV or Parquet exports by default. Snowflake documents a 24-hour cache for persisted query results; large-result access tokens can expire sooner. The broker, not the browser or model, should manage those details.

Never put a Snowflake result token, connector credential, presigned object URL, or bearer capability in the MCP response or browser URL.

## 3.6 Deterministic viewer

The viewer is a normal data application, not an AI component. It should:

- authenticate the human through enterprise SSO;
- authorize every request server-side and verify ownership or delegated access;
- list the signed-in user's recent query requests, avoiding a secret launch link in chat;
- render data with ordinary table code—no LLM summarization, embeddings, OCR, or model-generated labels;
- fetch either one policy-bounded Arrow stream or one authorized server-side page at a time from the broker;
- escape all cell values and column labels as untrusted content;
- enforce maximum columns, cell size, rows per page, and total rows;
- virtualize rendered tables and keep oversized resultsets out of browser memory;
- perform sorting and filtering either inside bounded DuckDB-Wasm memory or server-side under the same controls for oversized results;
- disable export initially, then add separately authorized and audited export if required;
- show classification, masking status, query owner, execution time, and expiration;
- expire sessions and results quickly;
- set strict Content Security Policy, `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, and clickjacking protections;
- avoid third-party analytics, session replay, crash reporters, support widgets, and CDN scripts that can observe cells;
- redact values from access logs, frontend telemetry, exception reports, and traces;
- prevent indexing and public sharing.

A safe user journey is:

1. The agent submits the query and receives `request_id`.
2. The coding-agent host shows a deterministic “Open governed results” action outside the model transcript, **or** the user opens a fixed internal viewer URL from a bookmark.
3. The viewer authenticates the user and shows their pending/completed requests.
4. The user opens the matching request and inspects pages of results.
5. The viewer records access and expires the result.

The fixed viewer URL is preferable to a signed result URL. If a URL appears in model context, assume the model may try to open it through a browser or HTTP tool. Authentication and authorization—not URL secrecy—must protect the data.

## 3.7 Arrow and DuckDB-Wasm viewer

The preferred interactive viewer can use Apache Arrow as the transport format and DuckDB-Wasm as an ephemeral browser-local analytical engine:

```diagram
┌─────────────────────────────────────────────────────────────────────┐
│ Human browser                                                       │
│                                                                     │
│  ┌──────────────────┐       page/query messages                     │
│  │ SPA UI thread    │◀─────────────────────────────────────────┐    │
│  │ grid and charts  │                                          │    │
│  └──────────────────┘                                          │    │
│                                                                │    │
│  ┌─────────────────────────────────────────────────────────────┴─┐  │
│  │ Web Worker                                                    │  │
│  │ Arrow batches → DuckDB-Wasm table → local SQL → visible page  │  │
│  └───────────────────────────────▲───────────────────────────────┘  │
└──────────────────────────────────┼──────────────────────────────────┘
                                   │ authenticated Arrow IPC stream
                          ┌────────┴────────┐
                          │ Result API      │
                          │ authorization   │
                          └────────┬────────┘
                                   │ server-held cursor/query identity
                          ┌────────▼────────┐
                          │ Snowflake       │
                          └─────────────────┘
```

### Data flow

1. The Query MCP submits SQL and returns an opaque, non-secret `request_id`.
2. The user opens a fixed internal SPA and authenticates with enterprise SSO.
3. The SPA lists requests authorized for that user; possession of `request_id` alone grants nothing.
4. The SPA requests the selected result from the Result API using an audience-bound human session.
5. The Result API rechecks ownership, delegation, current entitlement, status, and expiration on every request.
6. The API obtains server-held Snowflake result batches and streams Arrow IPC without exposing Snowflake query IDs, result tokens, or credentials to the browser.
7. A Web Worker decodes the batches and registers or inserts them into an in-memory DuckDB-Wasm table.
8. The viewer sends deterministic local queries to the worker for sorting, filtering, aggregation, charting, and pagination.
9. Only the requested display page or chart series returns to the UI thread. Nothing returns to MCP or the agent host.
10. Logout, expiration, explicit close, or tab termination destroys the in-memory database.

This preserves a useful analytical loop after the original query. A person can inspect data, issue follow-up SQL against the materialized result, derive temporary tables, and build deterministic visualizations without giving the LLM access and without repeatedly querying Snowflake.

### Browser controls

- Run DuckDB-Wasm and Arrow decoding in a dedicated Web Worker.
- Use in-memory storage by default. Disable IndexedDB, Origin Private File System, service-worker caching, and automatic workspace restoration unless separately governed.
- Apply strict dataset limits based on compressed bytes, decoded bytes, rows, columns, cell size, and estimated DuckDB memory—not only Snowflake row count.
- Use a fixed internal table name and constrain local SQL to that database. Do not expose URL readers, arbitrary file imports, external extensions, secrets, or network-capable functions.
- Restrict Content Security Policy `connect-src` to the Result API and avoid third-party scripts, fonts, analytics, crash reporters, and session replay.
- Keep values out of browser URLs, route state, page titles, notifications, clipboard defaults, telemetry, and exception messages.
- Escape cell and column content before DOM rendering. A value containing HTML or prompt-like instructions remains inert text.
- Return only a visible page from the worker to the UI to avoid unnecessary JavaScript and DOM copies.
- Make download, clipboard, print, and Arrow/CSV/Parquet export separately authorized, clearly labeled, rate-limited, and audited.
- Clear worker memory on logout and expiration. Document that browser process memory, developer tools, extensions, operating-system swap, and an already-authorized human remain part of the endpoint threat model.

### Large-result behavior

DuckDB-Wasm is excellent for bounded analytical datasets, not an excuse to send an entire warehouse extract to a browser. The browser must not be responsible for discovering that a result is too large: by then the bytes have crossed the network and may already have exhausted browser memory. Admission belongs in the query gateway and Result API.

```diagram
Agent SQL
    │
    ▼
┌──────────────────┐
│ SQL policy gate  │──reject unsafe or unbounded request
└────────┬─────────┘
         ▼
┌──────────────────┐
│ Snowflake        │──warehouse, timeout, credit, and concurrency limits
│ bounded query    │
└────────┬─────────┘
         ▼
┌──────────────────┐
│ Result gate      │──rows, Arrow bytes, cell size, memory estimate
└──────┬─────┬─────┘
       │     │
  fits │     │ too large
       ▼     ▼
 DuckDB-    Keep server-side;
 Wasm       require narrower query
```

#### Gate 1: impose a server-controlled result cap

Do not trust a model-supplied `LIMIT`. After parsing and validating the statement, the gateway should use an AST transformation to impose its own top-level cap while preserving query semantics. For an approved maximum of `K` rows, request `K + 1`. This conceptual wrapper illustrates the policy for `K = 100000`; production rewriting must preserve any ordering and existing limit semantics:

```sql
SELECT *
FROM (
    -- validated user query
) AS governed_result
LIMIT 100001; -- gateway-generated K + 1
```

- At most `K` rows means the result may proceed to the remaining admission checks.
- The presence of row `K + 1` means the result is oversized.
- Do not silently show the first `K` rows as if they were complete.
- If the product offers preview mode, label it explicitly as truncated and govern it separately.

The outer limit caps returned cardinality, not necessarily Snowflake work. An `ORDER BY`, window function, aggregation, or expensive join can process hundreds of millions of rows before producing `K + 1`. Query cost needs an independent gate.

Reject obviously dangerous patterns before execution, including an unbounded `SELECT *` against large base tables. This is a useful policy but not a complete control: explicitly naming every column can produce the same result size.

#### Gate 2: bound Snowflake computation

Execute under controls that remain effective even when a query returns few rows:

- a dedicated warehouse with a maximum approved size;
- statement and queued-query timeouts;
- resource monitors and credit limits;
- per-user and tenant concurrency and submission quotas;
- approved objects and functions only;
- cancellation when runtime policy is exceeded;
- narrower secure views or parameterized query templates for high-risk data products.

Prefer queries that project only needed columns and include selective predicates or aggregation. A 500-million-row interactive result is normally a query-design failure, not a browser-paging problem.

#### Gate 3: admit the completed result before browser release

Keep the result in Snowflake or the server-side broker until the gateway can inspect available result metadata. Apply limits to all of the following—not only row count:

- rows;
- columns;
- individual cell size;
- Arrow transport bytes;
- estimated decoded Arrow bytes;
- estimated DuckDB table and query working memory;
- endpoint or browser policy.

A narrow numeric table and a table containing large JSON or text values can have the same row count and radically different memory requirements. Serialized Arrow size is also lower than peak memory because decoding, strings, DuckDB structures, local query working space, JavaScript messages, and rendered pages may create additional copies.

If reliable size metadata is unavailable before retrieval, the Result API may read Arrow batches into a bounded server-side admission process. It must stop reading and close or cancel the cursor as soon as any server budget is exceeded. It must not use the browser as the measuring buffer.

#### Gate 4: enforce streaming limits and backpressure

Metadata can be wrong or incomplete, so count actual values at the Result API before forwarding each Arrow record batch:

```text
if rows_so_far + batch_rows > row_limit: abort
if arrow_bytes_so_far + batch_bytes > transport_limit: abort
if largest_cell_in_batch > cell_limit: abort
if estimated_peak_memory + batch_estimate > memory_limit: abort
```

Stream through a browser `ReadableStream` into the Web Worker one batch at a time. Backpressure should prevent the server from sending faster than the worker can ingest. Do not first download the entire response into one JavaScript `ArrayBuffer`, and do not retain redundant full copies in the main thread, Arrow objects, DuckDB, and the grid.

Browser ingestion should be provisional:

1. Load batches into a hidden temporary DuckDB table.
2. Keep the result unavailable to the grid while the stream is incomplete.
3. Require an authenticated completion marker from the Result API.
4. On overflow, truncation, cancellation, or integrity failure, terminate the worker and destroy the temporary database.
5. Publish the table to the viewer only after successful completion.

This means a late limit failure can leave at most the approved partial budget in isolated worker memory, never an accidentally accepted partial dataset.

#### Gate 5: give DuckDB-Wasm a hard memory budget

Set product limits for rows, Arrow bytes, estimated decoded memory, columns, maximum cell size, and reserved query working memory. For illustration only, a deployment might test limits such as 500,000 rows, 256 MB of Arrow, 768 MB of estimated peak memory, 250 columns, and 2 MB per cell. The actual values must come from benchmarks across every supported browser and endpoint class.

Do not set the Arrow limit equal to available memory. Reserve substantial headroom for:

- decoding and variable-length strings;
- DuckDB table structures;
- sorts, hashes, joins, and aggregations;
- WebAssembly and worker overhead;
- the visible grid and chart data;
- the browser and operating system.

Device-memory signals can help choose a lower policy tier, but they are incomplete and must not override server hard limits. On local overflow, terminate the worker; do not automatically spill to IndexedDB or OPFS.

Use explicit modes:

| Mode | Use | Behavior |
|---|---|---|
| Browser-local | Result fits approved memory/size budget | Stream Arrow into in-memory DuckDB-Wasm; all subsequent exploration is local |
| Server-paged | Result exceeds browser budget but row viewing is approved | Keep data server-side and return authorized pages; local DuckDB features are limited |
| Rejected or narrowed | Result exceeds policy, export, or cost limits | Ask the human to narrow the query; do not silently sample or spill sensitive data |

Server-side pagination can support deliberate inspection of selected rows, but it does not make hundreds of millions of rows meaningfully browsable. The normal response to a huge result should be to narrow, project, filter, or aggregate the Snowflake query. An approved large export is a separate workflow.

For example, if the agent submits `SELECT * FROM production.transactions`, the policy gate should reject it as an unbounded wildcard against a large base table. If it is allowed to execute under a capped wrapper, detection of row `K + 1` should classify it as too large before Arrow is released. The human viewer—not the MCP response—then explains that the query must be narrowed or routed through the governed export process.

Do not automatically persist oversized results to browser storage. If durable Arrow or Parquet artifacts become necessary, treat them as a new governed data product with encryption, retention, deletion, classification, and access auditing.

### Viewer libraries and avoiding row-oriented conversion

The viewer does **not** need to convert the full DuckDB result into JSON, JSON Lines, or an array of JavaScript row objects. DuckDB-Wasm uses Arrow for query results and offers two relevant patterns:

- `query()` materializes a query result as one Arrow table;
- `send()` returns results lazily as an Arrow record-batch stream.

The display layer can therefore ask DuckDB for only the visible window and read scalar values directly from Arrow vectors. The grid will eventually need JavaScript strings or numbers for the cells it paints, but conversion can be limited to tens or hundreds of visible cells instead of the entire dataset.

```diagram
┌──────────────────────┐
│ DuckDB-Wasm          │
│ full admitted result │
└──────────┬───────────┘
           │ SQL for visible window
           ▼
┌──────────────────────┐
│ Arrow record batches │  no JSON/JSONL materialization
│ small bounded cache  │
└──────────┬───────────┘
           │ vector.get(row) for visible cells only
           ▼
┌──────────────────────┐
│ Virtualized grid     │
│ canvas or small DOM  │
└──────────────────────┘
```

There is no honest claim of end-to-end zero-copy: WebAssembly and JavaScript have separate memory domains, and a painted DOM or canvas cell ultimately requires a JavaScript-visible scalar. The practical objective is **zero full-dataset row conversion**, bounded Arrow batches, transferable buffers where supported, and scalar conversion only at the viewport edge.

#### Recommended options

| Library | DuckDB/Arrow fit | Presentation | Memory characteristics | Recommendation |
|---|---|---|---|---|
| [UW Mosaic and vgplot](https://idl.uw.edu/mosaic/) | Native DuckDB-Wasm connector; components publish queries to the backing database | Coordinated charts, filters, inputs, and a sortable load-on-scroll table | DuckDB remains the analytical engine; the table requests rows on demand with a configurable batch size | Best integrated default for an analytical SPA |
| [Glide Data Grid](https://grid.glideapps.com/) | Data-source agnostic `getCellContent` callback; requires a thin Arrow viewport adapter | Highly polished canvas grid with fast scrolling, selection, editing, frozen columns, and custom cells | Lazily paints cells; cache only small Arrow windows and create cell objects only on demand | Best choice when table polish is the top priority; MIT licensed |
| [FINOS regular-table](https://github.com/finos/regular-table) | Async virtual rectangular data model can query DuckDB in a worker | Standards-based HTML table; fully CSS-themeable; fewer turnkey product features | Queries and renders only the visible rectangle; no dependency and no full row-object store | Best lightweight, framework-neutral option; Apache-2.0 licensed |
| [FINOS Perspective](https://perspective.finos.org/) | Direct Arrow ingestion, but uses its own WASM analytics engine rather than DuckDB | Most turnkey pivoting, grids, charts, dashboards, and saved layouts | Feeding the admitted base table to both DuckDB and Perspective usually creates a second analytical copy | Excellent if Perspective replaces DuckDB, or for small derived outputs; avoid duplicating the full base dataset |
| [AG Grid](https://www.ag-grid.com/) | Viewport and server-side row models can consume bounded blocks, but expect row-shaped values rather than Arrow vectors | Very mature enterprise grid and feature set | Conversion can be limited to the current block, but there is no direct full-dataset Arrow path; advanced row models are commercial | Viable commercial alternative, not the most columnar-native fit |

Mosaic is unusually well aligned with this architecture. Its coordinator can use DuckDB-Wasm as the database connector, plots push filtering and aggregation into DuckDB, and its table component is sortable and load-on-scroll. The table's `rowBatch` controls how many additional rows it queries as scrolling advances. This avoids maintaining a second browser analytics engine.

Glide Data Grid is the strongest option if the primary experience is a polished spreadsheet-like result grid. It does not natively accept an Arrow table, but its callback API is a useful boundary rather than a blocker: the application owns the data source and provides one cell on demand. A small adapter can keep Arrow batches columnar and convert only requested cells.

#### Recommended implementation pattern

Use one DuckDB-Wasm instance as the source of truth and put a viewport adapter between it and the grid:

1. The grid reports the visible row and column range plus overscan.
2. The adapter normalizes the active projection, filter, and sort into parameterized local SQL.
3. DuckDB executes a bounded query for that window.
4. Use the lazy Arrow record-batch result rather than `toArray()`, `toJSON()`, or a full-table `.map()`.
5. Keep a small least-recently-used cache of Arrow pages around the viewport.
6. Read visible values from Arrow column vectors and create only the cell descriptors needed by the renderer.
7. Cancel stale window queries when the user scrolls or changes sort/filter state.
8. Drop evicted Arrow buffers and enforce a separate display-cache byte budget.

Conceptually:

```text
viewport(start, end, columns, sort, filter)
    -> DuckDB SQL with bounded LIMIT/window
    -> lazy Arrow record batches
    -> Arrow page cache
    -> vector.get(local_row) for painted cells
```

For Glide, `getCellContent([column, row])` should synchronously read a cached Arrow vector. If the requested page is absent, return a loading cell, fetch the page asynchronously from the DuckDB worker, and invalidate only the affected cells when it arrives. For `regular-table`, its async data listener can request the visible rectangle directly. Mosaic's table already implements the database-backed load-on-scroll pattern.

Sorting, filtering, grouping, and aggregation should remain SQL operations in DuckDB—not JavaScript array operations in the UI. Charts should query only their aggregate series rather than receiving every underlying row. Mosaic/vgplot is a strong fit for those coordinated charts; Perspective can be used for a small derived Arrow result when its richer pivot interface is worth the additional engine.

#### Memory rules for the display layer

- Never call a convenience API that materializes the full result as JavaScript objects.
- Keep the full admitted dataset in exactly one analytical engine whenever possible.
- Bound the Arrow page cache independently from the DuckDB memory budget.
- Cache columnar record batches, not row objects.
- Transfer batch buffers between workers when supported rather than cloning them; do not retain both owners.
- Keep overscan modest and cancel stale reads during fast scrolling.
- Query only displayed columns so hidden wide text or JSON columns do not enter the display cache.
- Return aggregate chart data sized to pixels or marks, not raw source cardinality.
- Measure peak memory with realistic strings, nulls, wide values, sorting, and rapid scroll—not only numeric demos.
- Treat export, copy-all, select-all, and browser search across all rows as separate operations; they must not force full JavaScript materialization.

#### Suggested product choice

Prototype two front ends against the same Arrow viewport adapter:

1. **Mosaic/vgplot-only:** fastest route to an integrated SQL-backed table and coordinated charts.
2. **Glide Data Grid plus Mosaic/vgplot:** strongest table experience while retaining DuckDB-native charts and cross-filtering.

Choose after measuring memory, scroll latency, accessibility, theming effort, and security behavior with representative data. Do not select Perspective solely because it accepts Arrow; verify whether its second engine's memory cost is acceptable or use it instead of DuckDB rather than alongside DuckDB.

### What the model is allowed to do

The language should remain precise:

- The model **submits** the Snowflake query.
- The model may **request that the deterministic viewer be opened**.
- The authenticated SPA **fetches and loads** Arrow.
- DuckDB-Wasm and the human **analyze the returned data**.

Saying “the model fetches data for the SPA” obscures the boundary. The fetch must be initiated and authorized in the human data plane, even if a host UI action makes the transition feel seamless.

---

# 4. Return contracts

## Zero-context tool response

Use a strict output schema with no extensible fields:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "status": { "enum": ["accepted", "rejected"] },
    "request_id": { "type": "string", "pattern": "^[A-Z0-9]{20,32}$" },
    "reason_code": {
      "enum": ["NONE", "INVALID_REQUEST", "POLICY_REJECTED", "SERVICE_UNAVAILABLE"]
    }
  },
  "required": ["status", "request_id", "reason_code"]
}
```

Important details:

- `accepted` means only that the request entered the governed execution path. It need not reveal whether the query returned rows.
- `request_id` is an opaque correlator, not a Snowflake query ID and not a bearer secret.
- `reason_code` comes from a fixed allowlist and contains no SQL fragments, object names, values, driver messages, stack traces, or policy internals.
- response size is capped and schema-validated at the final serialization boundary.
- stdout and stderr from the Snowflake driver are captured and discarded or routed to a restricted operational sink after redaction; they are never copied into the tool result.
- all unexpected exceptions become the same generic response. Detailed errors are visible only to authorized operators or in the human viewer when safe.

If the agent needs syntax feedback before execution, offer a separate local SQL parser/linter that works from the submitted SQL alone. It should not ask Snowflake for error details. Snowflake compilation errors can reveal object names, function behavior, policy details, and sometimes values.

## Approved-analysis tools are separate products

If the model should receive totals, data-quality statuses, or statistical output, expose narrow tools such as:

```text
check_daily_balance(published_date) -> { status: PASS | FAIL | SUPPRESSED }
portfolio_totals(published_date)    -> approved fixed aggregate schema
```

Each requires its own disclosure review, minimum-cell thresholds, suppression logic, differencing protections, rate limits, and tests. Do not add a general `summarize_result(request_id)` escape hatch; that simply moves the leak to a second tool.

---

# 5. Threat model and controls

| Failure path | Example | Required control |
|---|---|---|
| Normal MCP result | Rows serialized as JSON | Fixed zero-data output schema; final response allowlist |
| Structured or embedded MCP content | Rows placed in `structuredContent`, image, or resource | Prohibit these result types for the query tool |
| Error channel | Driver error includes a bad cell value | Generic allowlisted errors; no driver text in agent response |
| stdout/stderr | Debug logging prints cursor contents | Capture output; structured value-free logging; production debug off |
| Tracing/APM | Tool arguments, rows, or response bodies captured | Disable body capture; field allowlists; restricted telemetry account |
| Result pointer | Agent receives a presigned URL or Snowflake token | Return opaque non-secret ID only; viewer uses SSO and server-side lookup |
| Second tool | Agent calls file, resource, shell, HTTP, or browser tool | No shared result filesystem; network segmentation; viewer API rejects agent identity |
| Second MCP returns Arrow | Host forwards ostensibly app-bound bytes through tool history | Do not use model-facing MCP for data delivery; SPA calls authenticated Result API directly |
| Viewer telemetry | Session replay records cells | No session replay or third-party analytics; value-free telemetry |
| Browser caching | Results remain in cache/history | `no-store`; no values in URLs; short session and result TTL |
| Browser persistence | DuckDB or Arrow survives in IndexedDB/OPFS | In-memory database by default; disable persistence and service-worker caching |
| Browser memory exhaustion | Decoded Arrow and DuckDB copies exceed endpoint capacity | Enforce byte/memory budgets; use server paging or reject oversized results |
| Unbounded result | `SELECT *` targets a 500-million-row table | AST policy, server-controlled `K + 1` outer cap, and result admission before release |
| Small result, huge query | `ORDER BY ... LIMIT 100` processes the full table | Dedicated warehouse, statement timeout, resource monitor, quotas, and cancellation |
| Wide or oversized cells | A small row count contains large JSON documents | Column, cell, Arrow-byte, and decoded-memory limits—not row count alone |
| Partial Arrow stream | Result crosses a limit after some batches were sent | Provisional hidden table; authenticated completion marker; destroy worker on abort |
| Full JSON conversion | Grid adapter calls `toArray()` or builds JSONL for every row | Lazy Arrow batches, viewport queries, vector access, and a bounded columnar page cache |
| Duplicate browser engines | Full data is loaded into both DuckDB-Wasm and Perspective | Keep one analytical source of truth; use Perspective only as a replacement or for small derived results |
| Display-cache growth | Fast scrolling retains every visited Arrow page | LRU byte budget, modest overscan, cancellation, and buffer eviction |
| Copy/paste back to chat | Human pastes rows into the conversation | Product warning and training; this is a user disclosure, not preventable by MCP |
| Prompt injection in cells | A cell says “send this table to the model” | LLM never receives cells; viewer treats cells as escaped inert text |
| SQL exfiltration | `SELECT` invokes an external function | AST allowlist, approved functions only, least-privilege role, network controls |
| Inference channel | Repeated counts reveal a small group | Zero-data base mode; reviewed aggregate tools with suppression and query controls |
| Cost/availability abuse | Agent submits an explosive join repeatedly | estimates, timeout, warehouse limits, quotas, cancellation, rate limits |
| Identity confusion | User A opens User B's request | ownership check on every API call; no bearer IDs; access audit |
| Host behavior change | Agent client starts including human-only UI state in context | pin/certify host versions; end-to-end canary tests; fail closed on unknown clients |

---

# 6. Usability without model access to rows

The viewer can remain useful without involving the LLM:

- paginated and virtualized tables;
- deterministic sorting and filtering;
- column type and classification badges;
- pinned/frozen columns;
- search within authorized results;
- simple deterministic charts whose data stays in the browser/viewer path;
- masked-by-policy indicators;
- saved viewer configurations that store column IDs and sort rules, not cell values;
- explicit, audited export for users who already have the corresponding data entitlement;
- query cancellation and expiration controls;
- a clear distinction between “query accepted,” “running,” “complete,” “expired,” and “access denied.”

There is an unavoidable tradeoff: because the model does not see the results, it cannot inspect an unexpected row, infer why a join duplicated records, or automatically revise SQL based on values. Preserve a productive loop through deterministic, non-data feedback:

- local SQL parsing and formatting;
- schema contracts supplied from a reviewed, non-sensitive catalog;
- compile-only or explain-plan checks whose output has been separately approved;
- tests that return fixed `PASS`, `FAIL`, or `SUPPRESSED` codes;
- human-authored feedback such as “the join duplicated rows,” without pasting values;
- narrow approved aggregate tools where model interpretation creates enough value to justify disclosure.

The goal is not to pretend there is no usability cost. It is to make each disclosure an explicit product and governance decision instead of an accidental property of a generic query tool.

---

# 7. Delivery plan

## Phase 0: settle policy before code

1. Define whether the promise is “no row values” or “no result-derived information.”
2. Classify allowed Snowflake data and identify prohibited domains.
3. Decide whether arbitrary read SQL is truly required. Prefer approved secure views and parameterized query templates when they meet the use case.
4. Identify the exact coding-agent hosts and tools that could form alternate read paths.
5. Define result retention, export, audit, and incident-response requirements.

## Phase 1: proof of boundary

Build the smallest vertical slice:

- remote MCP gateway;
- one `submit_read_query` tool;
- one dedicated read-only Snowflake role and warehouse;
- AST allowlist for a single `SELECT`;
- opaque request registry;
- short-lived cursor or persisted Snowflake result;
- SSO-protected SPA and Result API;
- bounded Arrow IPC streaming into in-memory DuckDB-Wasm in a Web Worker;
- generic receipts and errors only;
- no persistence, export, sharing, third-party telemetry, or MCP App.

Use synthetic data containing unique canary strings. Verify that a person can see the canaries in the viewer while none appear in the agent transcript, model requests, MCP logs, host traces, shell output, browser URLs, application logs, metrics, or error reporting.

## Phase 2: hardening

- add row and column policies in Snowflake;
- add per-user delegated identity if it was not in the proof of concept;
- implement quotas, timeouts, cancellation, and abuse controls;
- test malicious SQL and dangerous functions;
- conduct an authorization review for cross-user access;
- add automated retention and deletion verification;
- certify specific agent-host versions and fail closed for unknown clients;
- run penetration testing against the viewer and gateway;
- create alerts for policy rejection spikes, cross-user attempts, export attempts, and unusual query volume.

## Phase 3: controlled usability

Add only features justified by user need:

- deterministic charts;
- audited export;
- approved metadata catalog;
- narrow aggregate/status tools;
- optional host-integrated “Open results” action that is demonstrably outside model context.

Treat an MCP App as a later optimization only after proving app-only data separation in the selected host.

---

# 8. Verification and acceptance criteria

The system should not be approved based only on code review. Test the information flow end to end.

## Automated contract tests

- Tool responses match the strict output schema byte-for-byte except for approved fields.
- Property-based tests feed canary values through rows, column names, errors, Unicode, binary values, and very large cells.
- No canary appears in stdout, stderr, logs, traces, metrics labels, MCP responses, resources, notifications, or task status.
- Driver exceptions always map to allowlisted reason codes.
- The MCP server offers no result-reading resource or tool.
- Request IDs are random correlators with no embedded identity or query information.

## Authorization tests

- Another user cannot list, open, page, sort, filter, cancel, or export the request.
- An unauthenticated browser, copied URL, agent HTTP tool, and service identity cannot retrieve rows.
- Expired and revoked sessions fail closed.
- Snowflake role escalation, warehouse selection, and unapproved object access fail.

## Host/context tests

- Capture the exact payload sent from the host to the model after tool execution and verify absence of canaries.
- Inspect conversation persistence, prompt cache inputs, tool history, observability, crash reports, and UI previews.
- Repeat after host upgrades; do not assume behavior remains constant.
- Disable or separately test screenshots, accessibility extraction, browser automation, and “summarize this screen” features.

## Viewer tests

- Cell content is escaped and cannot execute HTML or script.
- Values never appear in URLs, page titles, analytics, referrers, or exception text.
- Responses use `Cache-Control: no-store` and appropriate browser security headers.
- Pagination and exports enforce authorization on every request.
- Retention jobs actually make results unavailable after expiration.
- Arrow bytes travel directly from the Result API to the authenticated SPA and never appear in MCP or host captures.
- DuckDB-Wasm runs without browser persistence, external data access, or unapproved extensions.
- Browser memory limits produce a server-paged or rejected result rather than an uncontrolled spill or crash.
- A 500-million-row canary query is rejected or its browser result is blocked by the `K + 1` cap before any Arrow reaches the browser; compute controls are verified separately.
- Queries with low output cardinality but expensive scans are stopped by Snowflake compute and timeout controls.
- Large cells and highly variable row widths are rejected by byte and memory limits even when row count is below threshold.
- A stream that crosses its limit midway never becomes visible; the worker and provisional database are destroyed.
- Backpressure prevents the browser fetch layer from buffering the entire Arrow response ahead of DuckDB ingestion.
- Grid scrolling converts only visible cells and keeps Arrow page-cache memory below its independent budget.
- No viewer code path invokes full-table `toArray()`, `toJSON()`, JSONL serialization, or equivalent row materialization.
- Sorting and filtering execute in DuckDB and do not build full JavaScript arrays.
- Loading the selected viewer does not create a second full analytical copy unless that mode was explicitly approved and budgeted.

## Acceptance statement

A defensible acceptance statement would be:

> For certified host and server versions, seeded query-result canaries are visible to the authorized user only in the governed viewer and are absent from all captured model inputs and agent-visible return channels. The MCP query tool returns only a schema-constrained receipt. Snowflake and viewer authorization are enforced independently, and alternate result-reading paths are denied.

Avoid an unqualified claim such as “the model can never see data.” A person can still paste it into chat, an administrator can misconfigure a policy, or a future host can change its behavior. Name the certified boundary and continuously test it.

---

# 9. Key design decisions

| Decision | Recommendation | Why |
|---|---|---|
| Where should rows be displayed? | Separate deterministic viewer | Cleanest human-only data path and easiest to audit |
| Should rows pass through MCP? | No | Normal MCP flow is designed to make tool results available to the client/model |
| Should a second MCP fetch Arrow? | No, not through a model-facing tool result | A second MCP does not create information-flow separation |
| How should a bounded result reach the browser? | Authenticated Result API streaming Arrow IPC | Efficient direct data plane with no model transit |
| How should the browser analyze it? | In-memory DuckDB-Wasm in a Web Worker | Deterministic local SQL, sorting, filtering, and charting without repeated Snowflake access |
| Who decides whether a result fits? | Query gateway and Result API before release | The browser is too late to serve as the primary admission control |
| How should row cardinality be capped? | Server-controlled outer `LIMIT K + 1` | Detects overflow without trusting model-authored SQL or silently truncating |
| Are row limits sufficient? | No; enforce bytes, cell size, peak-memory estimate, and Snowflake compute limits | Wide rows and expensive low-cardinality queries fail differently |
| Which integrated viewer best matches DuckDB-Wasm? | Prototype Mosaic/vgplot first | It directly coordinates DuckDB-backed queries, charts, filters, and load-on-scroll tables |
| Which grid offers the most polished table? | Glide Data Grid with an Arrow viewport adapter | Lazy canvas cells avoid a full row store while providing a strong grid experience |
| Should results be converted to JSONL for display? | No | Query bounded Arrow batches and convert only visible scalars at paint time |
| Should Perspective receive the full DuckDB dataset? | Normally no | Its separate WASM analytics engine can duplicate the primary browser data copy |
| Should the MCP tool return a result URL? | No bearer or signed result URL | URLs enter context and may be opened by another tool |
| Should it return counts/schema? | Not in zero-context mode | They are result-derived and can disclose information |
| Should results be written to local files? | No | Coding agents commonly have file and shell access |
| Should the first version support arbitrary SQL? | Prefer not; otherwise narrow parsed read-only SQL | Templates and approved views are much easier to govern |
| Should we use an MCP App? | Not initially | Current app flow does not itself prove model/data separation |
| Where should primary authorization live? | Snowflake plus viewer/gateway, both | Defense in depth and correct data entitlements |
| How should results be retained? | Short-lived cursor or Snowflake persisted result | Minimizes creation of additional sensitive copies |
| Can the model analyze results? | Only through separately approved narrow tools | Makes disclosure explicit and testable |

---

# 10. Bottom line

The design is feasible, but it is not “an MCP server that returns rows differently.” It is a **dual-channel system**:

- the LLM uses MCP as a control plane;
- Snowflake and a result broker form the governed data plane;
- a Result API streams Arrow directly into an in-memory DuckDB-Wasm viewer as the human presentation and local-analysis plane;
- the only object crossing back to the agent is a non-secret receipt.

That distinction extends the principle in the companion documents: the model sees what comes back, so do not send the data back. If humans still need the data, give them a separate, authenticated route that the agent cannot use.

---

## References

### Companion documents in this repository

- [Keeping data out of the context window](data-context-guardrails.html)
- [The model sees what comes back](data-context-leader-guide.html)

### External documentation

- Model Context Protocol, [Tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)—tool result types, normal client/model flow, output validation, and security considerations.
- Model Context Protocol, [MCP Apps](https://modelcontextprotocol.io/docs/extensions/apps)—current app architecture, host-mediated result flow, iframe isolation, and client support.
- Model Context Protocol, [Authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)—authorization requirements for HTTP-based MCP transports.
- Snowflake, [Using Persisted Query Results](https://docs.snowflake.com/en/user-guide/querying-persisted-results)—result retention, reuse, and access-token lifetime.
- Snowflake, [Understanding row access policies](https://docs.snowflake.com/en/user-guide/security-row-intro)—source-level row filtering.
- Snowflake, [Introduction to column-level security](https://docs.snowflake.com/en/user-guide/security-column-intro)—masking and column protection.
- Snowflake, [Access History](https://docs.snowflake.com/en/user-guide/access-history)—query/object access and policy audit data.
- DuckDB, [DuckDB-Wasm](https://duckdb.org/docs/current/clients/wasm/overview.html)—running DuckDB in browsers and loading/querying browser-local data.
- DuckDB, [DuckDB-Wasm Arrow input and lazy query results](https://duckdb.org/2021/10/29/duckdb-wasm.html)—direct Arrow IPC ingestion, Arrow query output, and lazy record-batch streaming with `send()`.
- Apache Arrow, [Columnar format specification](https://arrow.apache.org/docs/format/Columnar.html)—the language-independent in-memory format underlying efficient result transfer.
- UW Interactive Data Lab, [Mosaic](https://idl.uw.edu/mosaic/) and [Mosaic table](https://idl.uw.edu/mosaic/api/inputs/table.html)—DuckDB-backed coordinated views and a sortable table that loads rows on demand.
- Glide, [Glide Data Grid](https://github.com/glideapps/glide-data-grid)—MIT-licensed canvas grid with lazy cell callbacks and data-source-agnostic virtualization.
- FINOS, [regular-table](https://github.com/finos/regular-table)—Apache-2.0 virtual table with an async rectangular data model.
- FINOS, [Perspective](https://perspective.finos.org/)—Arrow-capable WASM analytics engine and polished configurable viewer.
