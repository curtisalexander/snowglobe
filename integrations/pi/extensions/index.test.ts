import assert from "node:assert/strict";
import test from "node:test";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { registerSnowglobe } from "./index.ts";

const requestId = "abcdefghijklmnopqrstuvwx";

function registeredTools(output: string) {
  const tools: Array<{
    name: string;
    parameters: { additionalProperties?: boolean };
    execute: (...args: unknown[]) => Promise<{ content: Array<{ type: string; text: string }> }>;
  }> = [];
  const pi = { registerTool: (tool: (typeof tools)[number]) => tools.push(tool) };
  const runner = async () => output;
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
    { sql: "SQL_CANARY", purpose: "PURPOSE_CANARY", requested_ttl: 300 },
    undefined,
  );
  const receipt = JSON.parse(result.content[0].text);
  assert.equal(receipt.status, "rejected");
  assert.equal(receipt.reason_code, "SERVICE_UNAVAILABLE");
  assert.doesNotMatch(result.content[0].text, /RESULT_VALUE_CANARY|SQL_CANARY|PURPOSE_CANARY/);
});

test("passes exact lifecycle receipts through unchanged", async () => {
  const receipt = { request_id: requestId, status: "complete" };
  const tools = registeredTools(JSON.stringify(receipt));
  const result = await tools[1].execute("call-id", { request_id: requestId }, undefined);
  assert.deepEqual(JSON.parse(result.content[0].text), receipt);
});

test("invokes the locked package CLI with SQL only on stdin", async () => {
  const calls: Array<{ command: string; args: string[]; stdin: string }> = [];
  const tools: Array<{
    execute: (...args: unknown[]) => Promise<{ content: Array<{ type: string; text: string }> }>;
  }> = [];
  const pi = { registerTool: (tool: (typeof tools)[number]) => tools.push(tool) };
  const runner = async (command: string, args: string[], stdin: string) => {
    calls.push({ command, args, stdin });
    return JSON.stringify({ status: "accepted", request_id: requestId, reason_code: "NONE" });
  };
  registerSnowglobe(pi as unknown as ExtensionAPI, runner);

  await tools[0].execute(
    "call-id",
    { sql: "SQL_STDIN_CANARY", purpose: "bounded analysis", requested_ttl: 300 },
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
