# ADR 0006: Incremental Arrow admission for the synthetic proof

- **Status:** Accepted for the synthetic proof
- **Date:** August 18, 2026

## Context

The Result API cannot trust model-authored limits, source metadata, or the browser to
decide whether a result is safe to release. It must measure actual Arrow batches
without concatenating the result or converting it into Python row dictionaries. A
late violation must preserve the failure-atomic completion contract from ADR 0005.

The supported endpoint memory tiers and representative datasets are not yet known,
so the illustrative limits in the architecture proposal must not become runtime
defaults.

## Decision

- Synthetic sources expose one stable PyArrow schema and asynchronously yield
  `RecordBatch` objects. Schema changes and non-record-batch values are rejected.
- Require explicit positive limits for rows, columns, maximum cell bytes, serialized
  Arrow bytes, and cumulative decoded Arrow bytes. The deployable deny-all app has no
  implicit result limits; a local stream without configured limits returns
  a fixed service-unavailable response.
- Validate column count and supported types before opening the IPC stream. The
  synthetic proof initially accepts null, Boolean, integer, floating-point, decimal,
  date, time, timestamp, duration, UTF-8 string, and binary scalar types. It rejects
  nested, dictionary, union, extension, and other unreviewed types.
- Before serializing each batch:
  - add its actual row count and `RecordBatch.nbytes` to cumulative counters;
  - measure variable-width string and binary cells directly from Arrow offset buffers;
  - use physical width for fixed-width scalar cells; and
  - reject the batch if any row, decoded-byte, or cell limit is crossed.
- Serialize through one Arrow IPC stream writer into a drainable batch-local sink.
  Count the actual serialized bytes, including schema and end-of-stream bytes, before
  releasing each chunk.
- Keep only writer state and the current serialized batch chunk server-side. Never
  collect all batches, concatenate a complete result, call `to_pylist()`, build row
  dictionaries, or fall back to row retrieval.
- Raise one detail-free internal admission error. The Result API omits ADR 0005's
  terminal completion frame for any admission or source failure and never serializes
  the reason into the response.
- Preserve schema for an admitted empty result by emitting a valid empty Arrow IPC
  stream before the Snowglobe completion frame.

## Consequences

- Row, column, scalar-cell, Arrow-transport, and decoded-Arrow budgets are enforced
  from actual data rather than source claims.
- A late violating batch is never released. Earlier admitted chunks may exist only in
  provisional worker state and cannot be published without the terminal frame.
- PyArrow is now a core backend dependency because admission is part of the synthetic
  Result API boundary, independent of Snowflake connectivity.
- Nested and dictionary-encoded results fail closed until their cell-size and decoded
  memory accounting receive a separate review.
- `RecordBatch.nbytes` is a decoded Arrow allocation measure, not a complete browser
  peak-memory model. DuckDB, worker transfer, query workspace, and display cache need
  independent budgets and representative benchmarks before production values are set.
