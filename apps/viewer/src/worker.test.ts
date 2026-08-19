import { describe, expect, it } from "vitest";

import { startDatabaseWorker, stateFromMessage } from "./worker";

class FakeWorker {
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: Worker["onerror"] = null;
  readonly messages: Array<Record<string, unknown>> = [];
  terminated = false;
  failOnChunk = false;

  postMessage(message: Record<string, unknown>): void {
    this.messages.push(message);
    queueMicrotask(() => {
      if (message.type === "initialize") {
        this.emit({ type: "ready" });
      } else if (message.type === "destroy" || message.type === "abort") {
        this.emit({ type: "destroyed" });
      } else if (message.type === "stream-chunk" && this.failOnChunk) {
        this.emit({ type: "failed" });
      } else {
        if (message.type === "stream-end") this.emit({ type: "published" });
        this.emit({ type: "ack", sequence: message.sequence });
      }
    });
  }

  terminate(): void {
    this.terminated = true;
  }

  private emit(data: Record<string, unknown>): void {
    this.onmessage?.({ data } as MessageEvent);
  }
}

function stream(...chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
}

describe("database worker messages", () => {
  it("maps only lifecycle messages to visible states", () => {
    expect(stateFromMessage("ready")).toBe("ready");
    expect(stateFromMessage("published")).toBe("ready");
    expect(stateFromMessage("failed")).toBe("failed");
    expect(stateFromMessage("viewport")).toBe("starting");
    expect(stateFromMessage("contains-data")).toBe("starting");
  });

  it("destroys the one-result worker if another request tries to reuse it", async () => {
    const underlying = new FakeWorker();
    const worker = startDatabaseWorker(() => undefined, () => underlying);

    await worker.load(stream(new Uint8Array([1])), 1024);
    await expect(worker.load(stream(new Uint8Array([2])), 1024)).rejects.toThrow(
      "Database worker unavailable",
    );
    await new Promise<void>((resolve) => queueMicrotask(() => resolve()));

    expect(underlying.messages.at(-1)?.type).toBe("abort");
    expect(underlying.terminated).toBe(true);
  });

  it("cancels input and terminates after a stream or overflow failure", async () => {
    const underlying = new FakeWorker();
    underlying.failOnChunk = true;
    let cancelled = false;
    const input = new ReadableStream<Uint8Array>({
      pull(controller) {
        controller.enqueue(new Uint8Array([1]));
      },
      cancel() {
        cancelled = true;
      },
    });
    const states: string[] = [];
    const worker = startDatabaseWorker((state) => states.push(state), () => underlying);

    await expect(worker.load(input, 1)).rejects.toThrow("Database worker unavailable");

    expect(cancelled).toBe(true);
    expect(states).toContain("failed");
    expect(underlying.terminated).toBe(true);
  });

  it("requests database destruction when the viewer closes", async () => {
    const underlying = new FakeWorker();
    const worker = startDatabaseWorker(() => undefined, () => underlying);
    await new Promise<void>((resolve) => queueMicrotask(() => resolve()));

    worker.destroy();
    await new Promise<void>((resolve) => queueMicrotask(() => resolve()));

    expect(underlying.messages.at(-1)?.type).toBe("destroy");
    expect(underlying.terminated).toBe(true);
  });
});
