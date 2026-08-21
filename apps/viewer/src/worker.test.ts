import { describe, expect, it } from "vitest";

import { startDatabaseWorker } from "./worker";

class FakeWorker {
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: Worker["onerror"] = null;
  readonly messages: Array<Record<string, unknown>> = [];
  terminated = false;
  failOnLoad = false;
  holdLoad = false;

  postMessage(message: Record<string, unknown>): void {
    this.messages.push(message);
    queueMicrotask(() => {
      if (message.type === "initialize") {
        this.emit({ type: "ready" });
      } else if (message.type === "destroy" || message.type === "abort") {
        this.emit({ type: "destroyed" });
      } else if (message.type === "load" && this.failOnLoad) {
        this.emit({ type: "failed" });
      } else if (message.type === "load" && this.holdLoad) {
        return;
      } else if (message.type === "viewport") {
        this.emit({
          type: "viewport",
          sequence: message.sequence,
          viewport: { columns: ["value"], rows: [["ok"]], hasMore: false },
        });
      } else {
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

describe("database worker messages", () => {
  it("destroys the one-result worker if another request tries to reuse it", async () => {
    const underlying = new FakeWorker();
    const worker = startDatabaseWorker(() => undefined, () => underlying);

    await worker.load("abcdefghijklmnopqrstuvwx");
    await expect(worker.load("zyxwvutsrqponmlkjihgfedc")).rejects.toThrow(
      "Database worker unavailable",
    );
    await new Promise<void>((resolve) => queueMicrotask(() => resolve()));

    expect(underlying.messages.at(-1)?.type).toBe("abort");
    expect(underlying.terminated).toBe(true);
  });

  it("terminates after a result load failure", async () => {
    const underlying = new FakeWorker();
    underlying.failOnLoad = true;
    const states: string[] = [];
    const worker = startDatabaseWorker((state) => states.push(state), () => underlying);

    await expect(worker.load("abcdefghijklmnopqrstuvwx")).rejects.toThrow(
      "Database worker unavailable",
    );

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

  it("rejects an active load when the viewer closes", async () => {
    const underlying = new FakeWorker();
    underlying.holdLoad = true;
    const worker = startDatabaseWorker(() => undefined, () => underlying);
    const loading = worker.load("abcdefghijklmnopqrstuvwx");
    await new Promise<void>((resolve) => queueMicrotask(() => resolve()));

    worker.destroy();

    await expect(loading).rejects.toThrow("Database worker unavailable");
  });

  it("returns a correlated viewport reply", async () => {
    const worker = startDatabaseWorker(() => undefined, () => new FakeWorker());
    await worker.load("abcdefghijklmnopqrstuvwx");

    await expect(worker.viewport(0, 50)).resolves.toEqual({
      columns: ["value"],
      rows: [["ok"]],
      hasMore: false,
    });
  });
});
