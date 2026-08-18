import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace

import pyarrow as pa
import pytest

from snowglobe.arrow_stream import (
    ArrowAdmissionError,
    ArrowAdmissionLimits,
    admitted_ipc_chunks,
)

TEST_LIMITS = ArrowAdmissionLimits(
    maximum_rows=100,
    maximum_columns=10,
    maximum_cell_bytes=1024,
    maximum_arrow_bytes=1024 * 1024,
    maximum_decoded_bytes=1024 * 1024,
)


@dataclass
class Source:
    schema: pa.Schema
    batches: tuple[object, ...]

    async def open(self) -> AsyncIterator[pa.RecordBatch]:
        for batch in self.batches:
            yield batch  # type: ignore[misc]


def string_batch(values: list[str | None], name: str = "value") -> pa.RecordBatch:
    return pa.record_batch([pa.array(values, type=pa.string())], names=[name])


def collect(
    source: Source,
    limits: ArrowAdmissionLimits | None = None,
) -> tuple[list[bytes], bool]:
    async def run() -> tuple[list[bytes], bool]:
        chunks = []
        try:
            async for chunk in admitted_ipc_chunks(source, limits or TEST_LIMITS):
                chunks.append(chunk)
        except ArrowAdmissionError as error:
            assert str(error) == ""
            return chunks, False
        return chunks, True

    return asyncio.run(run())


def test_serializes_multiple_batches_as_one_incremental_ipc_stream() -> None:
    first = string_batch(["alpha", None])
    second = string_batch(["beta"])

    chunks, admitted = collect(Source(first.schema, (first, second)))

    assert admitted
    assert len(chunks) == 3
    reader = pa.ipc.open_stream(b"".join(chunks))
    assert reader.schema == first.schema
    assert reader.read_next_batch().num_rows == 2
    assert reader.read_next_batch().column(0)[0].as_py() == "beta"


def test_empty_result_preserves_schema_and_completes() -> None:
    schema = pa.schema([("CANARY_COLUMN", pa.int64())])

    chunks, admitted = collect(Source(schema, ()))

    assert admitted
    reader = pa.ipc.open_stream(b"".join(chunks))
    assert reader.schema == schema
    with pytest.raises(StopIteration):
        reader.read_next_batch()


@pytest.mark.parametrize(
    ("source", "limits"),
    [
        (
            Source(string_batch(["a", "b"]).schema, (string_batch(["a", "b"]),)),
            replace(TEST_LIMITS, maximum_rows=1),
        ),
        (
            Source(string_batch(["éé"]).schema, (string_batch(["éé"]),)),
            replace(TEST_LIMITS, maximum_cell_bytes=3),
        ),
        (
            Source(string_batch(["decoded"]).schema, (string_batch(["decoded"]),)),
            replace(TEST_LIMITS, maximum_decoded_bytes=1),
        ),
        (
            Source(string_batch(["transport"]).schema, (string_batch(["transport"]),)),
            replace(TEST_LIMITS, maximum_arrow_bytes=1),
        ),
        (
            Source(pa.schema([("a", pa.int8()), ("b", pa.int8())]), ()),
            replace(TEST_LIMITS, maximum_columns=1),
        ),
        (
            Source(pa.schema([("nested", pa.list_(pa.int64()))]), ()),
            TEST_LIMITS,
        ),
    ],
)
def test_rejects_any_admission_budget_or_unsupported_type(
    source: Source,
    limits: ArrowAdmissionLimits,
) -> None:
    chunks, admitted = collect(source, limits)

    assert not admitted
    assert chunks == []


def test_late_row_overflow_preserves_only_previously_admitted_batch() -> None:
    first = string_batch(["first"])
    second = string_batch(["second"])

    chunks, admitted = collect(
        Source(first.schema, (first, second)),
        replace(TEST_LIMITS, maximum_rows=1),
    )

    assert not admitted
    assert len(chunks) == 1
    reader = pa.ipc.open_stream(chunks[0])
    assert reader.read_next_batch().column(0)[0].as_py() == "first"


def test_variable_cell_limit_uses_byte_offsets_for_sliced_binary_arrays() -> None:
    values = pa.array([b"ignored-prefix", b"ok", b"four"], type=pa.binary()).slice(1)
    batch = pa.record_batch([values], names=["binary_value"])

    chunks, admitted = collect(
        Source(batch.schema, (batch,)),
        replace(TEST_LIMITS, maximum_cell_bytes=3),
    )

    assert not admitted
    assert chunks == []


def test_rejects_schema_changes_and_non_record_batches() -> None:
    expected = string_batch(["safe"])
    changed = string_batch(["RESULT_CANARY"], name="different")

    for invalid in (changed, object()):
        chunks, admitted = collect(Source(expected.schema, (invalid,)))
        assert not admitted
        assert chunks == []


def test_limits_must_be_positive() -> None:
    with pytest.raises(ValueError, match="Arrow admission limits must be positive"):
        replace(TEST_LIMITS, maximum_rows=0)
