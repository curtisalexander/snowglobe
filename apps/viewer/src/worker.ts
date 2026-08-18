export type WorkerState = "starting" | "ready" | "failed";

export function stateFromMessage(type: string): WorkerState {
  if (type === "ready") return "ready";
  if (type === "failed") return "failed";
  return "starting";
}

export function startDatabaseWorker(
  onState: (state: WorkerState) => void,
): () => void {
  const worker = new Worker(new URL("./duckdb.worker.ts", import.meta.url), {
    type: "module",
  });

  worker.onmessage = (event: MessageEvent<{ type: string }>) => {
    onState(stateFromMessage(event.data.type));
  };
  worker.onerror = () => onState("failed");
  worker.postMessage({ type: "initialize" });

  return () => {
    worker.postMessage({ type: "destroy" });
    worker.terminate();
  };
}
