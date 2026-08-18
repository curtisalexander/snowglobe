/// <reference lib="webworker" />

import * as duckdb from "@duckdb/duckdb-wasm";
import duckdbEhWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import duckdbEhWasm from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";
import duckdbMvpWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url";
import duckdbMvpWasm from "@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url";

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

self.onmessage = async (event: MessageEvent<{ type: "initialize" | "destroy" }>) => {
  if (event.data.type === "destroy") {
    if (database) {
      await database.terminate();
      database = undefined;
    }
    self.postMessage({ type: "destroyed" });
    return;
  }

  try {
    const bundle = await duckdb.selectBundle(bundles);
    const engineWorker = new Worker(bundle.mainWorker!);
    database = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), engineWorker);
    await database.instantiate(bundle.mainModule, bundle.pthreadWorker);
    self.postMessage({ type: "ready" });
  } catch {
    self.postMessage({ type: "failed" });
  }
};
