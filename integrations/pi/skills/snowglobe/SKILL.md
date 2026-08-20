---
name: snowglobe
description: Submits governed read-only Snowflake SQL through Snowglobe and polls opaque request lifecycle receipts without exposing query results. Use when an analyst asks Pi to query an approved Snowflake view with Snowglobe.
compatibility: Requires uv, the Snowglobe package, and a running loopback snowglobe-local service.
---

# Snowglobe

Use the `submit_read_query` and `get_query_status` tools supplied by the Snowglobe Pi
extension.

1. Draft one read-only query against an exact approved, fully qualified view.
2. Call `submit_read_query` with SQL, a non-empty purpose, and the requested TTL.
3. If accepted, retain the opaque `request_id` and poll `get_query_status` until it is
   terminal.
4. Report only the submission and lifecycle receipts. Tell the analyst to inspect a
   complete request in their local Snowglobe viewer.

Never use `bash`, `curl`, browser automation, screenshots, accessibility APIs, or
other tools to access Snowglobe `/v1` routes, result streams, viewer contents, browser
state, local profiles, private keys, Snowflake identifiers, or database errors. Never
claim to have seen or summarized the result. The human analyst owns result inspection.
