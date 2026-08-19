import { afterEach, describe, expect, it, vi } from "vitest";

import {
  listRequests,
  openResultStream,
  ResultApiError,
} from "./result-api";

afterEach(() => vi.unstubAllGlobals());

describe("Result API client", () => {
  it("lists only schema-valid request metadata with viewer credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          requests: [
            {
              request_id: "abcdefghijklmnopqrstuvwx",
              status: "complete",
              expires_at: "2026-08-19T12:00:00+00:00",
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(listRequests()).resolves.toEqual([
      {
        requestId: "abcdefghijklmnopqrstuvwx",
        status: "complete",
        expiresAt: "2026-08-19T12:00:00+00:00",
      },
    ]);
    expect(fetchMock).toHaveBeenCalledWith("/v1/requests", {
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
  });

  it.each([
    { requests: [{ request_id: "CANARY", status: "complete", expires_at: "now" }] },
    {
      requests: [
        {
          request_id: "abcdefghijklmnopqrstuvwx",
          status: "unknown",
          expires_at: "2026-08-19T12:00:00Z",
        },
      ],
    },
    { unexpected: [] },
  ])("rejects malformed list responses", async (body) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(listRequests()).rejects.toThrow(ResultApiError);
  });

  it("opens an authenticated no-store Arrow stream", async () => {
    const stream = new ReadableStream<Uint8Array>();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(stream, {
        status: 200,
        headers: {
          "Content-Type": "application/vnd.snowglobe.arrow-stream",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(openResultStream("abcdefghijklmnopqrstuvwx")).resolves.toBe(stream);
    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/requests/abcdefghijklmnopqrstuvwx/stream",
      {
        credentials: "include",
        cache: "no-store",
        headers: { Accept: "application/vnd.snowglobe.arrow-stream" },
      },
    );
  });

  it("rejects a non-Arrow response without exposing its body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("RESULT_CANARY", {
          status: 404,
          headers: { "Content-Type": "text/plain" },
        }),
      ),
    );

    await expect(openResultStream("abcdefghijklmnopqrstuvwx")).rejects.toThrow(
      ResultApiError,
    );
  });
});
