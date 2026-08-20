import asyncio
from dataclasses import replace

import pyarrow as pa
import pytest

from snowglobe.arrow_stream import (
    ArrowAdmissionError,
    ArrowAdmissionLimits,
    admit_record_batches,
    ipc_chunks,
)

TEST_LIMITS = ArrowAdmissionLimits(
    maximum_rows=100,
    maximum_columns=10,
    maximum_cell_bytes=1024,
    maximum_arrow_bytes=1024 * 1024,
    maximum_decoded_bytes=1024 * 1024,
)


def string_batch(values: list[str | None], name: str = "value") -> pa.RecordBatch:
    return pa.record_batch([pa.array(values, type=pa.string())], names=[name])


def test_admits_and_serializes_multiple_batches_once() -> None:
    first = string_batch(["alpha", None])
    second = string_batch(["beta"])
    source = admit_record_batches(first.schema, (first, second), TEST_LIMITS)

    async def collect() -> list[bytes]:
        return [chunk async for chunk in ipc_chunks(source, TEST_LIMITS.maximum_arrow_bytes)]

    reader = pa.ipc.open_stream(b"".join(asyncio.run(collect())))
    assert reader.schema == first.schema
    assert reader.read_next_batch().num_rows == 2
    assert reader.read_next_batch().column(0)[0].as_py() == "beta"


def test_empty_result_preserves_schema() -> None:
    schema = pa.schema([("CANARY_COLUMN", pa.int64())])
    source = admit_record_batches(schema, (), TEST_LIMITS)

    async def collect() -> bytes:
        return b"".join([chunk async for chunk in ipc_chunks(source, 1024 * 1024)])

    reader = pa.ipc.open_stream(asyncio.run(collect()))
    assert reader.schema == schema
    with pytest.raises(StopIteration):
        reader.read_next_batch()


@pytest.mark.parametrize(
    ("batch", "limits"),
    [
        (string_batch(["a", "b"]), replace(TEST_LIMITS, maximum_rows=1)),
        (string_batch(["éé"]), replace(TEST_LIMITS, maximum_cell_bytes=3)),
        (string_batch(["decoded"]), replace(TEST_LIMITS, maximum_decoded_bytes=1)),
        (string_batch(["transport"]), replace(TEST_LIMITS, maximum_arrow_bytes=1)),
    ],
)
def test_rejects_admission_budget_overflow(
    batch: pa.RecordBatch,
    limits: ArrowAdmissionLimits,
) -> None:
    with pytest.raises(ArrowAdmissionError, match=r"^$"):
        admit_record_batches(batch.schema, (batch,), limits)


def test_rejects_unsupported_schema_and_schema_changes() -> None:
    nested = pa.schema([("nested", pa.list_(pa.int64()))])
    with pytest.raises(ArrowAdmissionError, match=r"^$"):
        admit_record_batches(nested, (), TEST_LIMITS)

    first = string_batch(["safe"])
    changed = string_batch(["unsafe"], name="different")
    with pytest.raises(ArrowAdmissionError, match=r"^$"):
        admit_record_batches(first.schema, (first, changed), TEST_LIMITS)


def test_serialization_keeps_transport_byte_ceiling() -> None:
    batch = string_batch(["transport"])
    source = admit_record_batches(batch.schema, (batch,), TEST_LIMITS)

    async def consume() -> None:
        with pytest.raises(ArrowAdmissionError, match=r"^$"):
            async for _chunk in ipc_chunks(source, 1):
                pass

    asyncio.run(consume())


def test_limits_must_be_positive() -> None:
    with pytest.raises(ValueError, match="Arrow admission limits must be positive"):
        replace(TEST_LIMITS, maximum_rows=0)
