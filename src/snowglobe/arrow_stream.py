"""Incremental Arrow admission and IPC serialization for the human data path."""

import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import pyarrow as pa


class ArrowAdmissionError(Exception):
    """A deliberately detail-free Arrow admission failure."""


class ArrowBatchSource(Protocol):
    """A source with a stable schema that yields bounded Arrow record batches."""

    @property
    def schema(self) -> pa.Schema: ...

    def open(self) -> AsyncIterator[pa.RecordBatch]: ...


@dataclass(frozen=True, slots=True)
class ArrowAdmissionLimits:
    maximum_rows: int
    maximum_columns: int
    maximum_cell_bytes: int
    maximum_arrow_bytes: int
    maximum_decoded_bytes: int

    def __post_init__(self) -> None:
        if (
            min(
                self.maximum_rows,
                self.maximum_columns,
                self.maximum_cell_bytes,
                self.maximum_arrow_bytes,
                self.maximum_decoded_bytes,
            )
            <= 0
        ):
            raise ValueError("Arrow admission limits must be positive")


class _ChunkSink:
    """Minimal PyArrow sink that permits bounded draining after each batch."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self._position = 0
        self.closed = False

    def write(self, data: bytes | memoryview) -> int:
        chunk = bytes(data)
        self._chunks.append(chunk)
        self._position += len(chunk)
        return len(chunk)

    def tell(self) -> int:
        return self._position

    def writable(self) -> bool:
        return True

    def close(self) -> None:
        self.closed = True

    def drain(self) -> bytes:
        chunk = b"".join(self._chunks)
        self._chunks.clear()
        return chunk


async def admitted_ipc_chunks(
    source: ArrowBatchSource,
    limits: ArrowAdmissionLimits,
) -> AsyncIterator[bytes]:
    """Validate actual batches and yield one bounded Arrow IPC chunk at a time."""

    schema = source.schema
    _validate_schema(schema, limits)
    sink = _ChunkSink()
    writer = pa.ipc.new_stream(sink, schema)
    rows = 0
    decoded_bytes = 0
    arrow_bytes = 0
    writer_closed = False
    try:
        async for batch in source.open():
            if not isinstance(batch, pa.RecordBatch):
                raise ArrowAdmissionError
            if not batch.schema.equals(schema, check_metadata=True):
                raise ArrowAdmissionError

            rows += batch.num_rows
            decoded_bytes += batch.nbytes
            if rows > limits.maximum_rows or decoded_bytes > limits.maximum_decoded_bytes:
                raise ArrowAdmissionError
            if _maximum_cell_bytes(batch) > limits.maximum_cell_bytes:
                raise ArrowAdmissionError

            writer.write_batch(batch)
            chunk = sink.drain()
            arrow_bytes += len(chunk)
            if arrow_bytes > limits.maximum_arrow_bytes:
                raise ArrowAdmissionError
            if chunk:
                yield chunk

        writer.close()
        writer_closed = True
        chunk = sink.drain()
        arrow_bytes += len(chunk)
        if arrow_bytes > limits.maximum_arrow_bytes:
            raise ArrowAdmissionError
        if chunk:
            yield chunk
    finally:
        if not writer_closed:
            writer.close()


def _validate_schema(schema: pa.Schema, limits: ArrowAdmissionLimits) -> None:
    if len(schema) > limits.maximum_columns:
        raise ArrowAdmissionError
    for field in schema:
        _cell_width(field.type)


def _maximum_cell_bytes(batch: pa.RecordBatch) -> int:
    maximum = 0
    for column in batch.columns:
        width = _cell_width(column.type)
        if width is None:
            width = _maximum_variable_cell_bytes(column)
        maximum = max(maximum, width)
    return maximum


def _maximum_variable_cell_bytes(column: pa.Array) -> int:
    if len(column) == 0:
        return 0
    offsets = column.buffers()[1]
    if offsets is None:
        raise ArrowAdmissionError
    large = pa.types.is_large_binary(column.type) or pa.types.is_large_string(column.type)
    width = 8 if large else 4
    format_code = "<q" if large else "<i"
    maximum = 0
    for index in range(column.offset, column.offset + len(column)):
        start = struct.unpack_from(format_code, offsets, index * width)[0]
        end = struct.unpack_from(format_code, offsets, (index + 1) * width)[0]
        if end < start:
            raise ArrowAdmissionError
        maximum = max(maximum, end - start)
    return maximum


def _cell_width(data_type: pa.DataType) -> int | None:
    if pa.types.is_null(data_type):
        return 0
    if pa.types.is_boolean(data_type):
        return 1
    if (
        pa.types.is_binary(data_type)
        or pa.types.is_large_binary(data_type)
        or pa.types.is_string(data_type)
        or pa.types.is_large_string(data_type)
    ):
        return None
    if pa.types.is_fixed_size_binary(data_type):
        return data_type.byte_width
    if (
        pa.types.is_integer(data_type)
        or pa.types.is_floating(data_type)
        or pa.types.is_decimal(data_type)
        or pa.types.is_date(data_type)
        or pa.types.is_time(data_type)
        or pa.types.is_timestamp(data_type)
        or pa.types.is_duration(data_type)
    ):
        return (data_type.bit_width + 7) // 8
    raise ArrowAdmissionError
