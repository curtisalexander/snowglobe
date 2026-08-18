import { describe, expect, it } from "vitest";
import { tableFromArrays, tableFromIPC, tableToIPC } from "apache-arrow";

import {
  ProvisionalResult,
  ResultStreamError,
  ResultStreamParser,
} from "./result-stream";

const magic = new TextEncoder().encode("SNOWGLOBE-ARROW-STREAM\x01");

function frame(type: number, payload: Uint8Array = new Uint8Array()): Uint8Array {
  const framed = new Uint8Array(9 + payload.byteLength);
  const view = new DataView(framed.buffer);
  view.setUint8(0, type);
  view.setBigUint64(1, BigInt(payload.byteLength), false);
  framed.set(payload, 9);
  return framed;
}

function concatenate(...chunks: Uint8Array[]): Uint8Array {
  const combined = new Uint8Array(
    chunks.reduce((length, chunk) => length + chunk.byteLength, 0),
  );
  let offset = 0;
  for (const chunk of chunks) {
    combined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return combined;
}

describe("result stream parser", () => {
  it("extracts Arrow frames split across arbitrary transport chunks", () => {
    const canary = new TextEncoder().encode("VIEWER_CANARY");
    const body = concatenate(magic, frame(1, canary), frame(2));
    const parser = new ResultStreamParser(1024);
    const arrowChunks: Uint8Array[] = [];

    for (let offset = 0; offset < body.byteLength; offset += 2) {
      arrowChunks.push(...parser.push(body.subarray(offset, offset + 2)));
    }
    parser.finish();

    expect(arrowChunks).toHaveLength(1);
    expect(new TextDecoder().decode(arrowChunks[0])).toBe("VIEWER_CANARY");
  });

  it.each([
    ["wrong magic", concatenate(new TextEncoder().encode("NOT-SNOWGLOBE-STREAM----"), frame(2))],
    ["unknown frame", concatenate(magic, frame(3))],
    ["empty Arrow frame", concatenate(magic, frame(1), frame(2))],
    ["completion payload", concatenate(magic, frame(2, new Uint8Array([1])))],
    ["trailing bytes", concatenate(magic, frame(2), new Uint8Array([1]))],
  ])("rejects %s", (_description, body) => {
    const parser = new ResultStreamParser(1024);
    expect(() => parser.push(body)).toThrow(ResultStreamError);
  });

  it("rejects an oversized declared frame before buffering its payload", () => {
    const header = new Uint8Array(9);
    const view = new DataView(header.buffer);
    view.setUint8(0, 1);
    view.setBigUint64(1, 1025n, false);
    const parser = new ResultStreamParser(1024);

    expect(() => parser.push(concatenate(magic, header))).toThrow(ResultStreamError);
  });

  it.each([
    ["missing completion", concatenate(magic, frame(1, new Uint8Array([1])))],
    ["truncated header", concatenate(magic, frame(1, new Uint8Array([1])), new Uint8Array([2]))],
  ])("fails closed on %s at end of stream", (_description, body) => {
    const parser = new ResultStreamParser(1024);
    parser.push(body);
    expect(() => parser.finish()).toThrow(ResultStreamError);
  });
});

describe("provisional result", () => {
  it("inserts canary Arrow provisionally and publishes only after clean EOF", async () => {
    const inserted: Uint8Array[] = [];
    let published = false;
    const result = new ProvisionalResult(1024, {
      async insert(chunk) {
        inserted.push(chunk);
      },
      async publish() {
        published = true;
      },
    });
    const canary = tableToIPC(
      tableFromArrays({ value: ["VIEWER_CANARY"] }),
      "stream",
    );

    await result.push(concatenate(magic, frame(1, canary), frame(2)));
    expect(
      tableFromIPC(Uint8Array.from(inserted[0])).getChild("value")?.get(0),
    ).toBe("VIEWER_CANARY");
    expect(published).toBe(false);

    await result.finish();
    expect(published).toBe(true);
  });

  it("never publishes a truncated stream", async () => {
    let published = false;
    const result = new ProvisionalResult(1024, {
      async insert() {},
      async publish() {
        published = true;
      },
    });

    await result.push(concatenate(magic, frame(1, new Uint8Array([1]))));
    await expect(result.finish()).rejects.toThrow(ResultStreamError);
    expect(published).toBe(false);
  });
});
