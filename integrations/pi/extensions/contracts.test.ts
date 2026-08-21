import assert from "node:assert/strict";
import test from "node:test";
import {
  parseStatusReceipt,
  parseSubmissionReceipt,
  unavailableStatus,
  unavailableSubmission,
} from "./contracts.ts";

const requestId = "abcdefghijklmnopqrstuvwx";

test("accepts only exact submission receipts", () => {
  const receipt = {
    status: "accepted",
    request_id: requestId,
    reason_code: "NONE",
    governed_sql: "SELECT 1 LIMIT 51",
  };
  assert.deepEqual(parseSubmissionReceipt(JSON.stringify(receipt)), receipt);
  assert.equal(parseSubmissionReceipt(JSON.stringify({ ...receipt, rows: ["RESULT_CANARY"] })), undefined);
  assert.equal(
    parseSubmissionReceipt(
      JSON.stringify({ status: "rejected", request_id: requestId, reason_code: "NONE" }),
    ),
    undefined,
  );
  assert.equal(parseSubmissionReceipt(JSON.stringify({ ...receipt, governed_sql: null })), undefined);
  assert.deepEqual(
    parseSubmissionReceipt(
      JSON.stringify({
        status: "rejected",
        request_id: requestId,
        reason_code: "POLICY_REJECTED",
        governed_sql: null,
      }),
    ),
    {
      status: "rejected",
      request_id: requestId,
      reason_code: "POLICY_REJECTED",
      governed_sql: null,
    },
  );
});

test("accepts only exact lifecycle receipts", () => {
  const receipt = { request_id: requestId, status: "complete" };
  assert.deepEqual(parseStatusReceipt(JSON.stringify(receipt)), receipt);
  assert.equal(parseStatusReceipt(JSON.stringify({ ...receipt, row_count: 1 })), undefined);
  assert.equal(parseStatusReceipt("INTERNAL_ERROR_CANARY"), undefined);
});

test("fixed unavailable receipts contain only allowlisted fields", () => {
  assert.deepEqual(Object.keys(unavailableSubmission()).sort(), [
    "governed_sql",
    "reason_code",
    "request_id",
    "status",
  ]);
  assert.equal(unavailableSubmission().governed_sql, null);
  assert.deepEqual(unavailableStatus(requestId), {
    request_id: requestId,
    status: "service_unavailable",
  });
  const invalid = unavailableStatus("INVALID.STATUS.CANARY");
  assert.notEqual(invalid.request_id, "INVALID.STATUS.CANARY");
  assert.match(invalid.request_id, /^[A-Za-z0-9_-]{20,32}$/);
});
