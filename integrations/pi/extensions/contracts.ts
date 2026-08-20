import { randomBytes } from "node:crypto";

const requestIdPattern = /^[A-Za-z0-9_-]{20,32}$/;
const submissionKeys = ["reason_code", "request_id", "status"];
const statusKeys = ["request_id", "status"];

const reasonCodes = new Set([
  "NONE",
  "INVALID_REQUEST",
  "POLICY_REJECTED",
  "SERVICE_UNAVAILABLE",
]);
const lifecycleStatuses = new Set([
  "pending",
  "complete",
  "failed",
  "cancelled",
  "expired",
  "not_found",
  "service_unavailable",
]);

export interface SubmissionReceipt {
  status: "accepted" | "rejected";
  request_id: string;
  reason_code: "NONE" | "INVALID_REQUEST" | "POLICY_REJECTED" | "SERVICE_UNAVAILABLE";
}

export interface StatusReceipt {
  request_id: string;
  status:
    | "pending"
    | "complete"
    | "failed"
    | "cancelled"
    | "expired"
    | "not_found"
    | "service_unavailable";
}

function isExactObject(value: unknown, keys: string[]): value is Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  return JSON.stringify(Object.keys(value).sort()) === JSON.stringify(keys);
}

function parseJson(text: string): unknown {
  if (Buffer.byteLength(text, "utf8") > 4096) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

export function parseSubmissionReceipt(text: string): SubmissionReceipt | undefined {
  const value = parseJson(text);
  if (!isExactObject(value, submissionKeys)) return undefined;
  if (value.status !== "accepted" && value.status !== "rejected") return undefined;
  if (typeof value.request_id !== "string" || !requestIdPattern.test(value.request_id)) {
    return undefined;
  }
  if (typeof value.reason_code !== "string" || !reasonCodes.has(value.reason_code)) {
    return undefined;
  }
  if ((value.status === "accepted") !== (value.reason_code === "NONE")) return undefined;
  return value as unknown as SubmissionReceipt;
}

export function parseStatusReceipt(text: string): StatusReceipt | undefined {
  const value = parseJson(text);
  if (!isExactObject(value, statusKeys)) return undefined;
  if (typeof value.request_id !== "string" || !requestIdPattern.test(value.request_id)) {
    return undefined;
  }
  if (typeof value.status !== "string" || !lifecycleStatuses.has(value.status)) {
    return undefined;
  }
  return value as unknown as StatusReceipt;
}

function newRequestId(): string {
  return randomBytes(18).toString("base64url");
}

export function unavailableSubmission(): SubmissionReceipt {
  return {
    status: "rejected",
    request_id: newRequestId(),
    reason_code: "SERVICE_UNAVAILABLE",
  };
}

export function unavailableStatus(requestId: string): StatusReceipt {
  return {
    request_id: requestIdPattern.test(requestId) ? requestId : newRequestId(),
    status: "service_unavailable",
  };
}
