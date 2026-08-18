/// <reference lib="webworker" />

import * as duckdb from "@duckdb/duckdb-wasm";
import duckdbEhWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import duckdbEhWasm from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";
import duckdbMvpWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url";
import duckdbMvpWasm from "@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url";
import { ProvisionalResult } from "./result-stream";

const bundles: duckdb.DuckDBBundles = {
  mvp: {
    mainModule: duckdbMvpWasm,
    mainWorker: duckdbMvpWorker,
  },
  eh: {
    mainModule: duckdbEhWasm,
    mainWorker: duckdbEhWorker,
  },
};

let database: duckdb.AsyncDuckDB | undefined;
let connection: duckdb.AsyncDuckDBConnection | undefined;
let provisionalResult: ProvisionalResult | undefined;
const pendingTable = "_snowglobe_pending";
const publishedTable = "snowglobe_result";

type WorkerRequest =
  | { type: "initialize" | "destroy" | "abort"; sequence?: number }
  | { type: "stream-start"; maximumFrameBytes: number; sequence: number }
  | { type: "stream-chunk"; chunk: Uint8Array; sequence: number }
  | { type: "stream-end"; sequence: number };

async function destroyDatabase(): Promise<void> {
  provisionalResult = undefined;
  if (connection) {
    await connection.close().catch(() => undefined);
    connection = undefined;
  }
  if (database) {
    await database.terminate().catch(() => undefined);
    database = undefined;
  }
}

function acknowledge(sequence: number | undefined): void {
  if (sequence !== undefined) self.postMessage({ type: "ack", sequence });
}

self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  if (event.data.type === "destroy" || event.data.type === "abort") {
    await destroyDatabase();
    self.postMessage({ type: "destroyed" });
    self.close();
    return;
  }

  try {
    if (event.data.type === "initialize") {
      if (database) throw new Error("already initialized");
      const bundle = await duckdb.selectBundle(bundles);
      const engineWorker = new Worker(bundle.mainWorker!);
      database = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), engineWorker);
      await database.instantiate(bundle.mainModule, bundle.pthreadWorker);
      connection = await database.connect();
      self.postMessage({ type: "ready" });
      return;
    }
    if (!database || !connection) throw new Error("not initialized");
    const activeConnection = connection;

    if (event.data.type === "stream-start") {
      if (provisionalResult) throw new Error("stream already started");
      provisionalResult = new ProvisionalResult(event.data.maximumFrameBytes, {
        async insert(chunk) {
          await activeConnection.insertArrowFromIPCStream(chunk, {
            name: pendingTable,
          });
        },
        async publish() {
          await activeConnection.query(
            `ALTER TABLE "${pendingTable}" RENAME TO "${publishedTable}"`,
          );
        },
      });
    } else if (event.data.type === "stream-chunk") {
      if (!provisionalResult) throw new Error("stream not started");
      await provisionalResult.push(event.data.chunk);
    } else if (event.data.type === "stream-end") {
      if (!provisionalResult) throw new Error("stream not started");
      await provisionalResult.finish();
      provisionalResult = undefined;
      self.postMessage({ type: "published" });
    } else {
      throw new Error("unknown message");
    }
    acknowledge(event.data.sequence);
  } catch {
    await destroyDatabase();
    self.postMessage({ type: "failed" });
    self.close();
  }
};
