# ADR 0005: Failure-atomic synthetic result stream framing

- **Status:** Superseded in part by [ADR 0008](0008-single-analyst-loopback-runtime.md); framing remains accepted
- **Date:** August 18, 2026

## Context

An HTTP response can fail after some Arrow bytes have reached the browser. Publishing
those bytes as a result would silently turn truncation, cancellation, expiry, source
failure, or a late budget overflow into a partial dataset. HTTP trailers are not a
portable browser contract, and buffering the complete result in the Result API would
defeat incremental delivery and backpressure.

The production human identity provider is still undecided. The synthetic proof needs
an authorization seam without treating an unverified header or request body as an
identity claim.

## Decision

- Construct the Result API with an injected authentication adapter. The adapter must
  return already-verified `ViewerClaims`; the default deployable app denies all result
  access until a deployment-specific adapter is configured.
- Authorize list, open, cancel, and stream independently through the broker. Unknown,
  wrong-audience, wrong-owner, cancelled, and expired stream access uses a fixed,
  non-reflective denial.
- Wrap admitted Arrow IPC chunks in a versioned binary stream:
  - magic bytes `SNOWGLOBE-ARROW-STREAM` followed by version byte `0x01`;
  - each frame has a one-byte type and unsigned 64-bit big-endian payload length;
  - type `0x01` carries an Arrow IPC chunk;
  - one terminal type `0x02` frame with a zero-length payload proves completion; and
  - no bytes may follow the completion frame.
- Treat the terminal frame as authenticated by the audience-bound Result API response
  over the deployment's authenticated HTTPS channel. Do not add a client-shared HMAC
  secret that would provide no stronger server authentication than TLS.
- Recheck ownership, status, and expiry before releasing every source chunk and before
  emitting completion. Enforce the configured Arrow-byte ceiling incrementally.
- Omit completion on source error, invalid chunk, cancellation, expiry, authorization
  failure, truncation, or overflow. Never serialize the internal failure into the
  stream.
- Require the worker to keep ingested data provisional and destroy it unless the
  framing parser observes exactly one valid terminal completion frame.
- Feed the continuous Arrow IPC payload through Arrow JS incrementally. Re-encode
  only the current record batch as a complete batch-local IPC stream for DuckDB-Wasm,
  because its insertion API treats each call as a complete stream; never buffer or
  convert the complete result. Apply backpressure with at most one framed chunk
  queued ahead of the Arrow reader.
- Apply `Cache-Control: no-store`, a deny-by-default CSP, no-referrer, no-sniff, and
  frame-denial headers to every Result API response.

## Consequences

- The API can stream with backpressure while the worker has an unambiguous commit
  condition.
- The envelope is not raw Arrow IPC; the worker must incrementally remove framing
  before passing Arrow bytes to DuckDB-Wasm.
- The Arrow JS bridge holds only parser state and the current record batch. DuckDB
  remains the sole complete browser result copy.
- A late failure can leave partial bytes only in provisional worker state, never in a
  published table.
- Synthetic sources now supply Arrow record batches to the admission process defined
  by [ADR 0006](0006-incremental-arrow-admission.md), which must succeed before
  completion can be emitted.
- The injected authenticator is a test/deployment seam, not an OIDC implementation.
  Selecting and implementing production human authentication remains a Phase 0 input.
