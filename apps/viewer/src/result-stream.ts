const STREAM_MAGIC = new Uint8Array([
  0x53, 0x4e, 0x4f, 0x57, 0x47, 0x4c, 0x4f, 0x42, 0x45, 0x2d, 0x41, 0x52,
  0x52, 0x4f, 0x57, 0x2d, 0x53, 0x54, 0x52, 0x45, 0x41, 0x4d, 0x01,
]);
const FRAME_HEADER_BYTES = 9;
const ARROW_FRAME = 1;
const COMPLETE_FRAME = 2;

export class ResultStreamError extends Error {
  constructor() {
    super("Invalid result stream");
    this.name = "ResultStreamError";
  }
}

export class ResultStreamParser {
  readonly #maximumResultBytes: bigint;
  readonly #maximumBufferedBytes: number;
  #buffer: Uint8Array = new Uint8Array();
  #magicRead = false;
  #complete = false;
  #arrowBytes = 0n;

  constructor(maximumResultBytes: number) {
    const maximumProtocolBytes =
      STREAM_MAGIC.byteLength +
      FRAME_HEADER_BYTES +
      maximumResultBytes * (FRAME_HEADER_BYTES + 1);
    if (
      !Number.isSafeInteger(maximumResultBytes) ||
      maximumResultBytes <= 0 ||
      !Number.isSafeInteger(maximumProtocolBytes)
    ) {
      throw new ResultStreamError();
    }
    this.#maximumResultBytes = BigInt(maximumResultBytes);
    this.#maximumBufferedBytes = maximumProtocolBytes;
  }

  push(chunk: Uint8Array): Uint8Array[] {
    if (this.#complete && chunk.byteLength > 0) throw new ResultStreamError();
    if (this.#buffer.byteLength + chunk.byteLength > this.#maximumBufferedBytes) {
      throw new ResultStreamError();
    }
    this.#buffer = concatenate(this.#buffer, chunk);
    const arrowChunks: Uint8Array[] = [];

    if (!this.#magicRead) {
      if (this.#buffer.byteLength < STREAM_MAGIC.byteLength) return arrowChunks;
      for (let index = 0; index < STREAM_MAGIC.byteLength; index += 1) {
        if (this.#buffer[index] !== STREAM_MAGIC[index]) throw new ResultStreamError();
      }
      this.#buffer = this.#buffer.slice(STREAM_MAGIC.byteLength);
      this.#magicRead = true;
    }

    while (this.#buffer.byteLength >= FRAME_HEADER_BYTES) {
      const view = new DataView(
        this.#buffer.buffer,
        this.#buffer.byteOffset,
        this.#buffer.byteLength,
      );
      const frameType = view.getUint8(0);
      const payloadLength = view.getBigUint64(1, false);

      if (frameType === COMPLETE_FRAME) {
        if (payloadLength !== 0n) throw new ResultStreamError();
        this.#buffer = this.#buffer.slice(FRAME_HEADER_BYTES);
        if (this.#buffer.byteLength > 0) throw new ResultStreamError();
        this.#complete = true;
        break;
      }
      if (
        frameType !== ARROW_FRAME ||
        payloadLength === 0n ||
        payloadLength > this.#maximumResultBytes
      ) {
        throw new ResultStreamError();
      }
      if (payloadLength > BigInt(this.#buffer.byteLength - FRAME_HEADER_BYTES)) {
        break;
      }

      const payloadBytes = Number(payloadLength);
      this.#arrowBytes += payloadLength;
      if (this.#arrowBytes > this.#maximumResultBytes) throw new ResultStreamError();
      arrowChunks.push(
        this.#buffer.slice(FRAME_HEADER_BYTES, FRAME_HEADER_BYTES + payloadBytes),
      );
      this.#buffer = this.#buffer.slice(FRAME_HEADER_BYTES + payloadBytes);
    }

    return arrowChunks;
  }

  finish(): void {
    if (!this.#magicRead || !this.#complete || this.#buffer.byteLength !== 0) {
      throw new ResultStreamError();
    }
  }
}

export type ProvisionalArrowSink = {
  insert(chunk: Uint8Array): Promise<void>;
  publish(): Promise<void>;
};

export class ProvisionalResult {
  readonly #parser: ResultStreamParser;
  readonly #sink: ProvisionalArrowSink;

  constructor(maximumResultBytes: number, sink: ProvisionalArrowSink) {
    this.#parser = new ResultStreamParser(maximumResultBytes);
    this.#sink = sink;
  }

  async push(chunk: Uint8Array): Promise<void> {
    for (const arrowChunk of this.#parser.push(chunk)) {
      await this.#sink.insert(arrowChunk);
    }
  }

  async finish(): Promise<void> {
    this.#parser.finish();
    await this.#sink.publish();
  }
}

function concatenate(left: Uint8Array, right: Uint8Array): Uint8Array {
  if (left.byteLength === 0) return right.slice();
  if (right.byteLength === 0) return left;
  const combined = new Uint8Array(left.byteLength + right.byteLength);
  combined.set(left);
  combined.set(right, left.byteLength);
  return combined;
}
