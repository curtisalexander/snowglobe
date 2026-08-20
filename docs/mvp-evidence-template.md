# Connected MVP value-free evidence template

Copy this template to a private location outside the repository before filling it in.
Retain only the fields below. Do not record SQL, profile values, account/object names,
credentials, result values or columns, Snowflake query IDs, driver errors, request
timings, result sizes, query-history rows, screenshots, or usage values.

## Campaign

- Date:
- Snowglobe revision:
- Pi package revision (if used):
- Dedicated non-production environment confirmed: PASS / FAIL
- Expected grants independently confirmed: PASS / FAIL
- Resource monitor independently confirmed active: PASS / FAIL
- Loopback-only listeners confirmed: PASS / FAIL

## Connected cases

| Case | PASS / FAIL | Lifecycle or reason code only | Administrator confirms bounded execution and expected grants/usage |
|---|---|---|---|
| Connected preflight |  |  |  |
| Allowed bounded canary |  |  |  |
| Empty result |  |  |  |
| Multiple batches (or N/A under the runbook condition) |  |  |  |
| Row overflow |  |  |  |
| Column overflow |  |  |  |
| Cell overflow |  |  |  |
| Arrow or decoded-byte overflow |  |  |  |
| Mutation rejection |  | `POLICY_REJECTED` | No execution confirmed:  |
| Multiple-statement rejection |  | `POLICY_REJECTED` | No execution confirmed:  |
| Unapproved-object rejection |  | `POLICY_REJECTED` | No execution confirmed:  |
| Function rejection |  | `POLICY_REJECTED` | No execution confirmed:  |
| Stage rejection |  | `POLICY_REJECTED` | No execution confirmed:  |
| Tool-selected config rejection |  | `INVALID_REQUEST` | No execution confirmed:  |
| Statement timeout |  |  |  |
| Administrator-aborted pending query |  |  |  |
| Cancellation and repeated cancellation |  |  |  |
| Expiry |  |  |  |
| Graceful shutdown and restart |  |  |  |

## Boundary observations

- MCP text and structured content have equivalent closed fields: PASS / FAIL
- Result canaries absent from MCP traffic: PASS / FAIL
- CLI stdout is one closed receipt and stderr is sanitized: PASS / FAIL
- Result canaries absent from CLI output: PASS / FAIL
- Pi registers exactly two closed tools with one receipt in tool content: PASS / FAIL
- Result canaries absent from Pi tool content and details: PASS / FAIL
- SQL absent from MCP responses and ordinary output: PASS / FAIL
- Result-derived data and Snowflake details absent from logs, errors, and URLs: PASS / FAIL
- Result data absent from browser storage and service workers: PASS / FAIL
- Complete canary result visible only through the local viewer path: PASS / FAIL

## Local checks

Record only command, exit status, and summary count.

| Command | Exit status | Summary count |
|---|---|---|
| `uv run ruff format --check .` |  |  |
| `uv run ruff check .` |  |  |
| `uv run ty check` |  |  |
| `uv run pytest` |  |  |
| `npm run lint` |  |  |
| `npm run typecheck` |  |  |
| `npm test` |  |  |
| `npm run build` |  |  |

MVP release evidence passes only when every applicable row passes and no stopping
condition in the constrained runbook occurred.
