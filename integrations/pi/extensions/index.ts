import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import {
  parseStatusReceipt,
  parseSubmissionReceipt,
  unavailableStatus,
  unavailableSubmission,
} from "./contracts.ts";
import { runProcess } from "./process.ts";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const uvCommand = process.env.SNOWGLOBE_UV ?? "uv";

function cliArgs(...args: string[]): string[] {
  return ["run", "--project", packageRoot, "--frozen", "snowglobe", ...args];
}

export function registerSnowglobe(pi: ExtensionAPI, runner: typeof runProcess = runProcess) {
  pi.registerTool({
    name: "submit_read_query",
    label: "Submit Snowglobe read query",
    description:
      "Submit one governed Snowflake read query to the running local Snowglobe service. Returns only an opaque closed receipt; never returns query results.",
    promptSnippet: "Submit governed Snowflake reads without exposing result data",
    promptGuidelines: [
      "Use submit_read_query for governed Snowflake reads; never use bash or HTTP to access Snowglobe viewer routes, result streams, browser state, or local configuration.",
    ],
    parameters: Type.Object(
      {
        sql: Type.String({ minLength: 1 }),
        purpose: Type.String({ minLength: 1 }),
        requested_ttl: Type.Integer({ minimum: 1 }),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal) {
      const output = await runner(
        uvCommand,
        cliArgs("submit", "--purpose", params.purpose, "--ttl", String(params.requested_ttl)),
        params.sql,
        signal,
        45_000,
      );
      const receipt = (output && parseSubmissionReceipt(output)) || unavailableSubmission();
      return { content: [{ type: "text", text: JSON.stringify(receipt) }], details: {} };
    },
  });

  pi.registerTool({
    name: "get_query_status",
    label: "Get Snowglobe query status",
    description:
      "Poll one opaque Snowglobe request ID. Returns only the request ID and a coarse lifecycle state; never returns query results or result metadata.",
    parameters: Type.Object(
      {
        request_id: Type.String({ pattern: "^[A-Za-z0-9_-]{20,32}$" }),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal) {
      const output = await runner(
        uvCommand,
        cliArgs("status", params.request_id),
        "",
        signal,
        15_000,
      );
      const receipt = (output && parseStatusReceipt(output)) || unavailableStatus(params.request_id);
      return { content: [{ type: "text", text: JSON.stringify(receipt) }], details: {} };
    },
  });
}

export default registerSnowglobe;
