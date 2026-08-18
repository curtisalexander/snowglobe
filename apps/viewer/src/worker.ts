export type WorkerState = "starting" | "ready" | "failed";

type WorkerReply = { type: string; sequence?: number };
type PendingReply = { resolve(): void; reject(): void };

export type DatabaseWorker = {
  load(stream: ReadableStream<Uint8Array>, maximumFrameBytes: number): Promise<void>;
  destroy(): void;
};

export function stateFromMessage(type: string): WorkerState {
  if (type === "ready" || type === "published") return "ready";
  if (type === "failed") return "failed";
  return "starting";
}

export function startDatabaseWorker(
  onState: (state: WorkerState) => void,
): DatabaseWorker {
  const worker = new Worker(new URL("./duckdb.worker.ts", import.meta.url), {
    type: "module",
  });
  let failed = false;
  let sequence = 0;
  let markReady: () => void;
  const ready = new Promise<void>((resolve) => {
    markReady = resolve;
  });
  const replies = new Map<number, PendingReply>();

  worker.onmessage = (event: MessageEvent<WorkerReply>) => {
    if (event.data.type === "ack" && event.data.sequence !== undefined) {
      replies.get(event.data.sequence)?.resolve();
      replies.delete(event.data.sequence);
      return;
    }
    if (event.data.type === "destroyed") {
      failed = true;
      for (const reply of replies.values()) reply.reject();
      replies.clear();
      worker.terminate();
      return;
    }
    if (event.data.type === "ready") markReady();
    if (event.data.type === "failed") {
      failed = true;
      markReady();
      for (const reply of replies.values()) reply.reject();
      replies.clear();
      worker.terminate();
    }
    onState(stateFromMessage(event.data.type));
  };
  worker.onerror = () => {
    failed = true;
    markReady();
    for (const reply of replies.values()) reply.reject();
    replies.clear();
    onState("failed");
    worker.terminate();
  };
  worker.postMessage({ type: "initialize" });

  const send = (message: object, transfer: Transferable[] = []): Promise<void> => {
    if (failed) return Promise.reject(new Error("Database worker unavailable"));
    sequence += 1;
    return new Promise((resolve, reject) => {
      replies.set(sequence, {
        resolve,
        reject: () => reject(new Error("Database worker unavailable")),
      });
      worker.postMessage({ ...message, sequence }, transfer);
    });
  };

  return {
    async load(stream, maximumFrameBytes) {
      await ready;
      const reader = stream.getReader();
      try {
        await send({ type: "stream-start", maximumFrameBytes });
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          await send({ type: "stream-chunk", chunk: value }, [value.buffer]);
        }
        await send({ type: "stream-end" });
      } catch (error) {
        await reader.cancel().catch(() => undefined);
        if (!failed) worker.postMessage({ type: "abort" });
        throw error;
      } finally {
        reader.releaseLock();
      }
    },
    destroy() {
      if (failed) return;
      worker.postMessage({ type: "destroy" });
      markReady();
      failed = true;
      for (const reply of replies.values()) reply.reject();
      replies.clear();
    },
  };
}
