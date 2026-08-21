/// <reference lib="webworker" />

import * as duckdb from "@duckdb/duckdb-wasm";
import duckdbEhWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import duckdbEhWasm from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";
import duckdbMvpWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url";
import duckdbMvpWasm from "@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url";
import { createIncrementalArrowSink } from "./arrow-ingest";
import { maximumResultBytes, maximumViewportRows } from "./mvp-limits";
import { openResultStream } from "./result-api";
import { ProvisionalResult } from "./result-stream";
import { createViewport } from "./viewport";

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
let activeLoad: AbortController | undefined;
let shutdownRequested = false;
const pendingTable = "_snowglobe_pending";
const publishedTable = "snowglobe_result";

type WorkerRequest =
  | { type: "initialize" | "destroy" | "abort"; sequence?: number }
  | { type: "load"; requestId: string; sequence: number }
  | { type: "viewport"; offset: number; limit: number; sequence: number };

async function destroyDatabase(): Promise<void> {
  if (connection) {
    await connection.close().catch(() => undefined);
    connection = undefined;
  }
  if (database) {
    await database.terminate().catch(() => undefined);
    database = undefined;
  }
}

self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  if (event.data.type === "destroy" || event.data.type === "abort") {
    shutdownRequested = true;
    activeLoad?.abort();
    await destroyDatabase();
    self.postMessage({ type: "destroyed" });
    self.close();
    return;
  }

  try {
    if (event.data.type === "initialize") {
      if (database) throw new Error("already initialized");
      const bundle = await duckdb.selectBundle(bundles);
      if (shutdownRequested) return;
      const engineWorker = new Worker(bundle.mainWorker!);
      const initializingDatabase = new duckdb.AsyncDuckDB(
        new duckdb.VoidLogger(),
        engineWorker,
      );
      database = initializingDatabase;
      await initializingDatabase.instantiate(bundle.mainModule, bundle.pthreadWorker);
      if (shutdownRequested || database !== initializingDatabase) {
        await initializingDatabase.terminate().catch(() => undefined);
        return;
      }
      const initializingConnection = await initializingDatabase.connect();
      if (shutdownRequested || database !== initializingDatabase) {
        await initializingConnection.close().catch(() => undefined);
        await initializingDatabase.terminate().catch(() => undefined);
        return;
      }
      connection = initializingConnection;
      self.postMessage({ type: "ready" });
      return;
    }
    if (!database || !connection) throw new Error("not initialized");
    const activeConnection = connection;

    if (event.data.type === "load") {
      const controller = new AbortController();
      activeLoad = controller;
      const stream = await openResultStream(event.data.requestId, controller.signal);
      const loadingResult = new ProvisionalResult(
        maximumResultBytes,
        createIncrementalArrowSink(
          activeConnection,
          pendingTable,
          async () => {
            await activeConnection.query(
              `ALTER TABLE "${pendingTable}" RENAME TO "${publishedTable}"`,
            );
          },
        ),
      );
      const reader = stream.getReader();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          await loadingResult.push(value);
        }
        await loadingResult.finish();
      } catch (error) {
        await reader.cancel().catch(() => undefined);
        throw error;
      } finally {
        reader.releaseLock();
        if (activeLoad === controller) activeLoad = undefined;
      }
    } else if (event.data.type === "viewport") {
      if (
        !Number.isSafeInteger(event.data.offset) ||
        event.data.offset < 0 ||
        !Number.isSafeInteger(event.data.limit) ||
        event.data.limit <= 0 ||
        event.data.limit > maximumViewportRows
      ) {
        throw new Error("invalid viewport");
      }
      const table = await activeConnection.query(
        `SELECT * FROM "${publishedTable}" LIMIT ${event.data.limit + 1} OFFSET ${event.data.offset}`,
      );
      self.postMessage({
        type: "viewport",
        sequence: event.data.sequence,
        viewport: createViewport(table, event.data.limit, maximumResultBytes),
      });
      return;
    } else {
      throw new Error("unknown message");
    }
    self.postMessage({ type: "ack", sequence: event.data.sequence });
  } catch {
    await destroyDatabase();
    if (shutdownRequested) return;
    self.postMessage({ type: "failed" });
    self.close();
  }
};
