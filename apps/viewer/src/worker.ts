import type { Viewport } from "./viewport";

export type WorkerState = "starting" | "ready" | "failed";

type WorkerReply = { type?: unknown; sequence?: unknown; viewport?: Viewport };
type ReplyType = "ack" | "viewport";
type PendingReply = {
  type: ReplyType;
  resolve(value: unknown): void;
  reject(): void;
};
type WorkerHandle = Pick<Worker, "onmessage" | "onerror" | "postMessage" | "terminate">;

export type DatabaseWorker = {
  load(requestId: string): Promise<void>;
  viewport(offset: number, limit: number): Promise<Viewport>;
  destroy(): void;
};

export function startDatabaseWorker(
  onState: (state: WorkerState) => void,
  createWorker: () => WorkerHandle = () =>
    new Worker(new URL("./duckdb.worker.ts", import.meta.url), {
      type: "module",
    }),
): DatabaseWorker {
  const worker = createWorker();
  let failed = false;
  let loadStarted = false;
  let sequence = 0;
  let markReady: () => void;
  const ready = new Promise<void>((resolve) => {
    markReady = resolve;
  });
  const replies = new Map<number, PendingReply>();
  const rejectReplies = () => {
    for (const reply of replies.values()) reply.reject();
    replies.clear();
  };

  const fail = () => {
    if (failed) return;
    failed = true;
    markReady();
    rejectReplies();
    onState("failed");
    worker.terminate();
  };

  worker.onmessage = (event: MessageEvent<WorkerReply>) => {
    if (event.data.type === "ack" || event.data.type === "viewport") {
      if (!Number.isSafeInteger(event.data.sequence)) {
        fail();
        return;
      }
      const reply = replies.get(event.data.sequence as number);
      if (!reply || reply.type !== event.data.type) {
        fail();
        return;
      }
      reply.resolve(event.data.viewport);
      replies.delete(event.data.sequence as number);
      return;
    }
    if (event.data.type === "destroyed") {
      failed = true;
      rejectReplies();
      worker.terminate();
      return;
    }
    if (event.data.type === "failed") {
      fail();
      return;
    }
    if (event.data.type !== "ready") {
      fail();
      return;
    }
    markReady();
    onState("ready");
  };
  worker.onerror = fail;
  worker.postMessage({ type: "initialize" });

  const send = <T>(type: ReplyType, message: object): Promise<T> => {
    if (failed) return Promise.reject(new Error("Database worker unavailable"));
    sequence += 1;
    return new Promise((resolve, reject) => {
      replies.set(sequence, {
        type,
        resolve,
        reject: () => reject(new Error("Database worker unavailable")),
      });
      worker.postMessage({ ...message, sequence });
    });
  };

  return {
    async load(requestId) {
      if (loadStarted) {
        if (!failed) worker.postMessage({ type: "abort" });
        failed = true;
        markReady();
        rejectReplies();
        throw new Error("Database worker unavailable");
      }
      loadStarted = true;
      await ready;
      await send<void>("ack", { type: "load", requestId });
    },
    viewport(offset, limit) {
      return send<Viewport>("viewport", { type: "viewport", offset, limit });
    },
    destroy() {
      if (failed) return;
      worker.postMessage({ type: "destroy" });
      markReady();
      failed = true;
      rejectReplies();
    },
  };
}
