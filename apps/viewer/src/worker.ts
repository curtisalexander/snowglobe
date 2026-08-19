import type { Viewport } from "./viewport";

export type WorkerState = "starting" | "ready" | "failed";

type WorkerReply = { type: string; sequence?: number; viewport?: Viewport };
type PendingReply = { resolve(value: unknown): void; reject(): void };

export type DatabaseWorker = {
  load(stream: ReadableStream<Uint8Array>, maximumFrameBytes: number): Promise<void>;
  viewport(offset: number, limit: number): Promise<Viewport>;
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
    if (
      (event.data.type === "ack" || event.data.type === "viewport") &&
      event.data.sequence !== undefined
    ) {
      replies.get(event.data.sequence)?.resolve(event.data.viewport);
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

  const send = <T>(message: object, transfer: Transferable[] = []): Promise<T> => {
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
        await send<void>({ type: "stream-start", maximumFrameBytes });
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          await send<void>({ type: "stream-chunk", chunk: value }, [value.buffer]);
        }
        await send<void>({ type: "stream-end" });
      } catch (error) {
        await reader.cancel().catch(() => undefined);
        if (!failed) worker.postMessage({ type: "abort" });
        throw error;
      } finally {
        reader.releaseLock();
      }
    },
    viewport(offset, limit) {
      return send<Viewport>({ type: "viewport", offset, limit });
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
