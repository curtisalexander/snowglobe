import { Table, tableFromArrays, tableFromIPC, tableToIPC } from "apache-arrow";
import { describe, expect, it } from "vitest";

import { createIncrementalArrowSink } from "./arrow-ingest";

describe("incremental Arrow ingestion", () => {
  it("reframes a continuous Arrow stream as complete batch-local IPC", async () => {
    const complete = tableFromArrays({ label: ["first", "second"], count: [1, 2] });
    const source = new Table(
      complete.slice(0, 1).batches[0],
      complete.slice(1, 2).batches[0],
    );
    const ipc = tableToIPC(source, "stream");
    const inserted: Uint8Array[] = [];
    const createModes: Array<boolean | undefined> = [];
    let published = false;
    const sink = createIncrementalArrowSink(
      {
        async insertArrowFromIPCStream(chunk, options) {
          inserted.push(chunk);
          createModes.push(options.create);
        },
      },
      "pending",
      async () => {
        published = true;
      },
    );

    for (let offset = 0; offset < ipc.byteLength; offset += 7) {
      await sink.insert(ipc.subarray(offset, offset + 7));
    }
    expect(published).toBe(false);

    await sink.publish();

    expect(inserted).toHaveLength(2);
    expect(createModes).toEqual([true, false]);
    expect(inserted.map((chunk) => tableFromIPC(chunk).numRows)).toEqual([1, 1]);
    expect(
      inserted.flatMap((chunk) => [...tableFromIPC(chunk)]).map((row) => row.toJSON()),
    ).toEqual([...source].map((row) => row.toJSON()));
    expect(published).toBe(true);
  });

  it("does not publish an invalid Arrow stream", async () => {
    let published = false;
    const sink = createIncrementalArrowSink(
      {
        async insertArrowFromIPCStream() {},
      },
      "pending",
      async () => {
        published = true;
      },
    );

    await sink.insert(new TextEncoder().encode("INVALID_ARROW_CANARY"));
    await expect(sink.publish()).rejects.toBeDefined();
    expect(published).toBe(false);
  });
});
