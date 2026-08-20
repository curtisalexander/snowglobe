import type { Viewport } from "./viewport";

export type WorkerState = "starting" | "ready" | "failed";

type WorkerReply = { type?: unknown; sequence?: unknown; viewport?: unknown };
type ReplyType = "ack" | "viewport";
type PendingReply = {
  type: ReplyType;
  resolve(value: unknown): void;
  reject(): void;
};
type WorkerHandle = Pick<Worker, "onmessage" | "onerror" | "postMessage" | "terminate">;

export type DatabaseWorker = {
  load(stream: ReadableStream<Uint8Array>, maximumResultBytes: number): Promise<void>;
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
  let activeReader: ReadableStreamDefaultReader<Uint8Array> | null = null;

  const fail = () => {
    if (failed) return;
    failed = true;
    markReady();
    void activeReader?.cancel().catch(() => undefined);
    for (const reply of replies.values()) reply.reject();
    replies.clear();
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
      if (
        !reply ||
        reply.type !== event.data.type ||
        (reply.type === "viewport" && !isViewport(event.data.viewport))
      ) {
        fail();
        return;
      }
      reply.resolve(event.data.viewport);
      replies.delete(event.data.sequence as number);
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
      fail();
      return;
    }
    if (event.data.type !== "ready" && event.data.type !== "published") {
      fail();
      return;
    }
    onState(stateFromMessage(event.data.type));
  };
  worker.onerror = fail;
  worker.postMessage({ type: "initialize" });

  const send = <T>(
    type: ReplyType,
    message: object,
    transfer: Transferable[] = [],
  ): Promise<T> => {
    if (failed) return Promise.reject(new Error("Database worker unavailable"));
    sequence += 1;
    return new Promise((resolve, reject) => {
      replies.set(sequence, {
        type,
        resolve,
        reject: () => reject(new Error("Database worker unavailable")),
      });
      worker.postMessage({ ...message, sequence }, transfer);
    });
  };

  return {
    async load(stream, maximumResultBytes) {
      if (loadStarted) {
        if (!failed) worker.postMessage({ type: "abort" });
        failed = true;
        markReady();
        for (const reply of replies.values()) reply.reject();
        replies.clear();
        throw new Error("Database worker unavailable");
      }
      loadStarted = true;
      await ready;
      const reader = stream.getReader();
      activeReader = reader;
      try {
        await send<void>("ack", { type: "stream-start", maximumResultBytes });
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          await send<void>("ack", { type: "stream-chunk", chunk: value }, [value.buffer]);
        }
        await send<void>("ack", { type: "stream-end" });
      } catch (error) {
        await reader.cancel().catch(() => undefined);
        if (!failed) worker.postMessage({ type: "abort" });
        throw error;
      } finally {
        if (activeReader === reader) activeReader = null;
        reader.releaseLock();
      }
    },
    viewport(offset, limit) {
      return send<Viewport>("viewport", { type: "viewport", offset, limit });
    },
    destroy() {
      if (failed) return;
      void activeReader?.cancel().catch(() => undefined);
      worker.postMessage({ type: "destroy" });
      markReady();
      failed = true;
      for (const reply of replies.values()) reply.reject();
      replies.clear();
    },
  };
}

function isViewport(value: unknown): value is Viewport {
  if (
    typeof value !== "object" ||
    value === null ||
    !("columns" in value) ||
    !("rows" in value) ||
    !("hasMore" in value) ||
    !Array.isArray(value.columns) ||
    !value.columns.every((column) => typeof column === "string") ||
    !Array.isArray(value.rows) ||
    typeof value.hasMore !== "boolean"
  ) {
    return false;
  }
  const columnCount = value.columns.length;
  return value.rows.every(
    (row) =>
      Array.isArray(row) &&
      row.length === columnCount &&
      row.every((cell) => cell === null || typeof cell === "string"),
  );
}
