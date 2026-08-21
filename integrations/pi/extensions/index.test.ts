import assert from "node:assert/strict";
import test from "node:test";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { registerSnowglobe } from "./index.ts";

const requestId = "abcdefghijklmnopqrstuvwx";

function registeredTools(output: string, runner = async () => output) {
  const tools: Array<{
    name: string;
    parameters: { additionalProperties?: boolean };
    execute: (...args: unknown[]) => Promise<{
      content: Array<{ type: string; text: string }>;
      details: object;
    }>;
  }> = [];
  const pi = { registerTool: (tool: (typeof tools)[number]) => tools.push(tool) };
  registerSnowglobe(pi as unknown as ExtensionAPI, runner);
  return tools;
}

test("registers exactly the two closed Snowglobe tools", () => {
  const tools = registeredTools("");
  assert.deepEqual(
    tools.map((tool) => tool.name),
    ["submit_read_query", "get_query_status"],
  );
  assert.ok(tools.every((tool) => tool.parameters.additionalProperties === false));
});

test("does not pass malformed CLI result data into Pi context", async () => {
  const tools = registeredTools(
    JSON.stringify({
      status: "accepted",
      request_id: requestId,
      reason_code: "NONE",
      rows: ["RESULT_VALUE_CANARY"],
    }),
  );
  const result = await tools[0].execute(
    "call-id",
    { sql: "SQL_CANARY", requested_ttl: 300 },
    undefined,
  );
  const receipt = JSON.parse(result.content[0].text);
  assert.equal(receipt.status, "rejected");
  assert.equal(receipt.reason_code, "SERVICE_UNAVAILABLE");
  assert.doesNotMatch(result.content[0].text, /RESULT_VALUE_CANARY|SQL_CANARY/);
});

test("contains rejected runner errors for both model-facing tools", async () => {
  const canary = "REJECTED_RUNNER_ERROR_CANARY";
  const tools = registeredTools("", async () => {
    throw new Error(canary);
  });

  const submission = await tools[0].execute(
    "call-id",
    { sql: "SQL_CANARY", requested_ttl: 300 },
    undefined,
  );
  const status = await tools[1].execute("call-id", { request_id: requestId }, undefined);

  assert.deepEqual(JSON.parse(submission.content[0].text), {
    status: "rejected",
    request_id: JSON.parse(submission.content[0].text).request_id,
    reason_code: "SERVICE_UNAVAILABLE",
  });
  assert.deepEqual(JSON.parse(status.content[0].text), {
    request_id: requestId,
    status: "service_unavailable",
  });
  assert.doesNotMatch(submission.content[0].text + status.content[0].text, new RegExp(canary));
  assert.deepEqual(submission.details, {});
  assert.deepEqual(status.details, {});
});

test("passes an exact submission receipt with empty details", async () => {
  const receipt = { status: "accepted", request_id: requestId, reason_code: "NONE" };
  const tools = registeredTools(JSON.stringify(receipt));

  const result = await tools[0].execute(
    "call-id",
    { sql: "SELECT 1", requested_ttl: 300 },
    undefined,
  );

  assert.deepEqual(JSON.parse(result.content[0].text), receipt);
  assert.deepEqual(result.details, {});
});

test("passes exact lifecycle receipts through unchanged", async () => {
  const receipt = { request_id: requestId, status: "complete" };
  const tools = registeredTools(JSON.stringify(receipt));
  const result = await tools[1].execute("call-id", { request_id: requestId }, undefined);
  assert.deepEqual(JSON.parse(result.content[0].text), receipt);
});

test("rejects a lifecycle receipt for a different request", async () => {
  const tools = registeredTools(
    JSON.stringify({ request_id: "zyxwvutsrqponmlkjihgfedc", status: "complete" }),
  );
  const result = await tools[1].execute("call-id", { request_id: requestId }, undefined);
  assert.deepEqual(JSON.parse(result.content[0].text), {
    request_id: requestId,
    status: "service_unavailable",
  });
});

test("rejects lifecycle metadata and keeps details empty", async () => {
  const tools = registeredTools(
    JSON.stringify({ request_id: requestId, status: "complete", row_count: 1 }),
  );

  const result = await tools[1].execute("call-id", { request_id: requestId }, undefined);

  assert.deepEqual(JSON.parse(result.content[0].text), {
    request_id: requestId,
    status: "service_unavailable",
  });
  assert.deepEqual(result.details, {});
});

test("invokes the locked package CLI with SQL only on stdin", async () => {
  const calls: Array<{ command: string; args: string[]; stdin: string }> = [];
  const tools: Array<{
    execute: (...args: unknown[]) => Promise<{
      content: Array<{ type: string; text: string }>;
      details: object;
    }>;
  }> = [];
  const pi = { registerTool: (tool: (typeof tools)[number]) => tools.push(tool) };
  const runner = async (command: string, args: string[], stdin: string) => {
    calls.push({ command, args, stdin });
    return JSON.stringify({ status: "accepted", request_id: requestId, reason_code: "NONE" });
  };
  registerSnowglobe(pi as unknown as ExtensionAPI, runner);

  await tools[0].execute(
    "call-id",
    { sql: "SQL_STDIN_CANARY", requested_ttl: 300 },
    undefined,
  );

  assert.equal(calls.length, 1);
  assert.equal(calls[0].command, "uv");
  assert.deepEqual(calls[0].args.slice(0, 2), ["run", "--project"]);
  assert.ok(calls[0].args.includes("--frozen"));
  assert.ok(calls[0].args.includes("snowglobe"));
  assert.equal(calls[0].stdin, "SQL_STDIN_CANARY");
  assert.ok(!calls[0].args.includes("SQL_STDIN_CANARY"));
});
