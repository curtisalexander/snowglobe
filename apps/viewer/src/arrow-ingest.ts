import { RecordBatchReader, Table, tableToIPC } from "apache-arrow";

import type { ProvisionalArrowSink } from "./result-stream";

type ArrowInsertConnection = {
  insertArrowFromIPCStream(
    chunk: Uint8Array,
    options: { name: string; create?: boolean },
  ): Promise<void>;
};

export function createIncrementalArrowSink(
  connection: ArrowInsertConnection,
  tableName: string,
  maximumQueuedBytes: number,
  publishTable: () => Promise<void>,
): ProvisionalArrowSink {
  const chunks = new ArrowChunkQueue(maximumQueuedBytes);
  const ingestion = ingestRecordBatches(connection, tableName, chunks).then(
    () => ({ succeeded: true as const }),
    (error: unknown) => {
      chunks.fail(error);
      return { succeeded: false as const, error };
    },
  );

  return {
    async insert(chunk) {
      await chunks.push(chunk);
    },
    async publish() {
      chunks.close();
      const outcome = await ingestion;
      if (!outcome.succeeded) throw outcome.error;
      await publishTable();
    },
  };
}

async function ingestRecordBatches(
  connection: ArrowInsertConnection,
  tableName: string,
  stream: AsyncIterable<Uint8Array>,
): Promise<void> {
  const reader = await RecordBatchReader.from(stream);
  let insertedBatch = false;
  for await (const batch of reader) {
    await connection.insertArrowFromIPCStream(tableToIPC(new Table(batch), "stream"), {
      name: tableName,
      create: !insertedBatch,
    });
    insertedBatch = true;
  }
  if (!insertedBatch) {
    await connection.insertArrowFromIPCStream(
      tableToIPC(new Table(reader.schema), "stream"),
      { name: tableName, create: true },
    );
  }
}

type QueuedChunk = {
  chunk: Uint8Array;
  consumed(): void;
  rejected(error: unknown): void;
};

class ArrowChunkQueue implements AsyncIterable<Uint8Array> {
  readonly #maximumChunkBytes: number;
  readonly #queue: QueuedChunk[] = [];
  #wake: (() => void) | undefined;
  #closed = false;
  #failure: unknown;

  constructor(maximumChunkBytes: number) {
    this.#maximumChunkBytes = maximumChunkBytes;
  }

  push(chunk: Uint8Array): Promise<void> {
    if (this.#closed || this.#failure || chunk.byteLength > this.#maximumChunkBytes) {
      return Promise.reject(this.#failure ?? new Error("Arrow stream unavailable"));
    }
    return new Promise((consumed, rejected) => {
      this.#queue.push({ chunk, consumed, rejected });
      this.#notify();
    });
  }

  close(): void {
    this.#closed = true;
    this.#notify();
  }

  fail(error: unknown): void {
    this.#failure = error;
    for (const item of this.#queue.splice(0)) item.rejected(error);
    this.#notify();
  }

  async *[Symbol.asyncIterator](): AsyncIterableIterator<Uint8Array> {
    while (true) {
      if (this.#failure) throw this.#failure;
      const item = this.#queue.shift();
      if (item) {
        item.consumed();
        yield item.chunk;
      } else if (this.#closed) {
        return;
      } else {
        await new Promise<void>((resolve) => {
          this.#wake = resolve;
        });
      }
    }
  }

  #notify(): void {
    this.#wake?.();
    this.#wake = undefined;
  }
}
