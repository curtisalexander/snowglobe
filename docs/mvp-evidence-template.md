# Connected MVP boundary evidence template

This checklist tests Snowglobe's actual claim: result data stays out of MCP, CLI, and Pi
receipts while the browser viewer can display it. Keep credentials out of the evidence.
The connected campaign uses non-sensitive canaries, so screenshots or local diagnostics
may be retained when useful; they do not prove what entered model context.

## Campaign

- Date:
- Snowglobe revision:
- Pi package revision (if used):
- Dedicated non-production environment confirmed: PASS / FAIL
- Expected read-only grants confirmed: PASS / FAIL
- Resource limit confirmed active: PASS / FAIL
- Loopback-only listeners confirmed: PASS / FAIL

## Connected cases

| Case | PASS / FAIL | MCP/CLI/Pi lifecycle or reason code | Execution/viewer observation |
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
| Unknown table function or `RESULT_SCAN` rejection |  | `POLICY_REJECTED` | No execution confirmed:  |
| Local `GENERATOR` / `FLATTEN` |  |  | Viewer result correct:  |
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
- Accepted receipts contain exact governed SQL; rejected receipts contain `null`: PASS / FAIL
- Snowflake connector logger remains suppressed: PASS / FAIL
- Result data absent from browser storage and service workers: PASS / FAIL
- Complete canary result visible through the local viewer path: PASS / FAIL
- Main thread receives only lifecycle metadata and bounded viewport messages: PASS / FAIL

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
