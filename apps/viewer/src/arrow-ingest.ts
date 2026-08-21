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
  publishTable: () => Promise<void>,
): ProvisionalArrowSink {
  const chunks = new TransformStream<Uint8Array, Uint8Array>();
  const writer = chunks.writable.getWriter();
  const ingestion = ingestRecordBatches(connection, tableName, chunks.readable).then(
    () => ({ succeeded: true as const }),
    (error: unknown) => ({ succeeded: false as const, error }),
  );

  return {
    async insert(chunk) {
      await writer.write(chunk);
    },
    async publish() {
      await writer.close();
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
