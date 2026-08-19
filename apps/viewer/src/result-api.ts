export type RequestStatus =
  | "pending"
  | "complete"
  | "failed"
  | "cancelled"
  | "expired";

export type RequestSummary = {
  requestId: string;
  status: RequestStatus;
  expiresAt: string;
};

export class ResultApiError extends Error {
  constructor() {
    super("Local viewer backend unavailable");
    this.name = "ResultApiError";
  }
}

export async function listRequests(): Promise<RequestSummary[]> {
  const response = await fetch("/v1/requests", {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new ResultApiError();

  const body: unknown = await response.json().catch(() => {
    throw new ResultApiError();
  });
  if (!isRecord(body) || !Array.isArray(body.requests)) throw new ResultApiError();
  return body.requests.map(parseRequest);
}

export async function getRequest(requestId: string): Promise<RequestSummary> {
  const response = await fetch(`/v1/requests/${encodeURIComponent(requestId)}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new ResultApiError();
  const body: unknown = await response.json().catch(() => {
    throw new ResultApiError();
  });
  return parseRequest(body);
}

export async function openResultStream(
  requestId: string,
): Promise<ReadableStream<Uint8Array>> {
  const response = await fetch(
    `/v1/requests/${encodeURIComponent(requestId)}/stream`,
    {
      cache: "no-store",
      headers: { Accept: "application/vnd.snowglobe.arrow-stream" },
    },
  );
  if (
    !response.ok ||
    response.headers.get("content-type")?.split(";", 1)[0] !==
      "application/vnd.snowglobe.arrow-stream" ||
    response.body === null
  ) {
    await response.body?.cancel().catch(() => undefined);
    throw new ResultApiError();
  }
  return response.body;
}

function parseRequest(value: unknown): RequestSummary {
  if (
    !isRecord(value) ||
    typeof value.request_id !== "string" ||
    !/^[A-Za-z0-9_-]{20,32}$/.test(value.request_id) ||
    !isStatus(value.status) ||
    typeof value.expires_at !== "string" ||
    !Number.isFinite(Date.parse(value.expires_at))
  ) {
    throw new ResultApiError();
  }
  return {
    requestId: value.request_id,
    status: value.status,
    expiresAt: value.expires_at,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStatus(value: unknown): value is RequestStatus {
  return (
    value === "pending" ||
    value === "complete" ||
    value === "failed" ||
    value === "cancelled" ||
    value === "expired"
  );
}
