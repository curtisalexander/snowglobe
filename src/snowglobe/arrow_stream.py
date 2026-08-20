"""Incremental Arrow admission and IPC serialization for the human data path."""

import struct
from collections.abc import AsyncIterator, Iterable
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
class InMemoryArrowBatchSource:
    """A complete admitted result retained as bounded record batches."""

    schema: pa.Schema
    batches: tuple[pa.RecordBatch, ...]

    async def open(self) -> AsyncIterator[pa.RecordBatch]:
        for batch in self.batches:
            yield batch


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


class _AdmissionState:
    """Incremental validation and serialization shared by execution and streaming."""

    def __init__(self, schema: pa.Schema, limits: ArrowAdmissionLimits) -> None:
        _validate_schema(schema, limits)
        self._schema = schema
        self._limits = limits
        self._sink = _ChunkSink()
        self._writer = pa.ipc.new_stream(self._sink, schema)
        self._rows = 0
        self._decoded_bytes = 0
        self._arrow_bytes = 0
        self._closed = False

    def admit(self, batch: pa.RecordBatch) -> bytes:
        if self._closed or not isinstance(batch, pa.RecordBatch):
            raise ArrowAdmissionError
        if not batch.schema.equals(self._schema, check_metadata=True):
            raise ArrowAdmissionError

        self._rows += batch.num_rows
        self._decoded_bytes += batch.nbytes
        if (
            self._rows > self._limits.maximum_rows
            or self._decoded_bytes > self._limits.maximum_decoded_bytes
        ):
            raise ArrowAdmissionError
        if _maximum_cell_bytes(batch) > self._limits.maximum_cell_bytes:
            raise ArrowAdmissionError

        self._writer.write_batch(batch)
        return self._drain_within_limit()

    def finish(self) -> bytes:
        if self._closed:
            raise ArrowAdmissionError
        self._writer.close()
        self._closed = True
        return self._drain_within_limit()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._writer.close()

    def _drain_within_limit(self) -> bytes:
        chunk = self._sink.drain()
        self._arrow_bytes += len(chunk)
        if self._arrow_bytes > self._limits.maximum_arrow_bytes:
            raise ArrowAdmissionError
        return chunk


def admit_record_batches(
    schema: pa.Schema,
    batches: Iterable[pa.RecordBatch],
    limits: ArrowAdmissionLimits,
) -> InMemoryArrowBatchSource:
    """Incrementally admit and retain one complete bounded result for later replay."""

    state = _AdmissionState(schema, limits)
    admitted: list[pa.RecordBatch] = []
    finished = False
    try:
        for batch in batches:
            state.admit(batch)
            admitted.append(batch)
        state.finish()
        finished = True
    finally:
        if not finished:
            state.close()
    return InMemoryArrowBatchSource(schema=schema, batches=tuple(admitted))


async def ipc_chunks(
    source: ArrowBatchSource,
    maximum_bytes: int,
) -> AsyncIterator[bytes]:
    """Serialize an already-admitted source as bounded Arrow IPC chunks."""

    if maximum_bytes <= 0:
        raise ArrowAdmissionError
    sink = _ChunkSink()
    writer = pa.ipc.new_stream(sink, source.schema)
    written = 0
    finished = False
    try:
        async for batch in source.open():
            if not isinstance(batch, pa.RecordBatch) or not batch.schema.equals(
                source.schema, check_metadata=True
            ):
                raise ArrowAdmissionError
            writer.write_batch(batch)
            chunk = sink.drain()
            written += len(chunk)
            if written > maximum_bytes:
                raise ArrowAdmissionError
            if chunk:
                yield chunk

        writer.close()
        finished = True
        chunk = sink.drain()
        written += len(chunk)
        if written > maximum_bytes:
            raise ArrowAdmissionError
        if chunk:
            yield chunk
    finally:
        if not finished:
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
