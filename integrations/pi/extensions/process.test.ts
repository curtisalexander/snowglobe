import assert from "node:assert/strict";
import test from "node:test";
import { runProcess } from "./process.ts";

test("passes SQL through stdin and captures bounded stdout", async () => {
  const output = await runProcess(
    process.execPath,
    ["-e", "process.stdin.pipe(process.stdout)"],
    "SELECT_FROM_STDIN_CANARY",
    undefined,
    5_000,
  );
  assert.equal(output, "SELECT_FROM_STDIN_CANARY");
});

test("does not return stderr or oversized output", async () => {
  const stderr = await runProcess(
    process.execPath,
    ["-e", "process.stderr.write('PRIVATE_ERROR_CANARY'); process.exit(1)"],
    "",
    undefined,
    5_000,
  );
  assert.equal(stderr, undefined);

  const oversized = await runProcess(
    process.execPath,
    ["-e", "process.stdout.write('x'.repeat(5000))"],
    "",
    undefined,
    5_000,
  );
  assert.equal(oversized, undefined);
});

test("fails closed on nonzero exit and timeout", async () => {
  const nonzero = await runProcess(
    process.execPath,
    ["-e", "process.stdout.write('PRIVATE_STDOUT_CANARY'); process.exit(2)"],
    "",
    undefined,
    5_000,
  );
  assert.equal(nonzero, undefined);

  const timedOut = await runProcess(
    process.execPath,
    ["-e", "setTimeout(() => {}, 10_000)"],
    "",
    undefined,
    20,
  );
  assert.equal(timedOut, undefined);
});

test("honors an aborted Pi tool call", async () => {
  const controller = new AbortController();
  const running = runProcess(
    process.execPath,
    ["-e", "setTimeout(() => {}, 10_000)"],
    "",
    controller.signal,
    5_000,
  );
  controller.abort();
  assert.equal(await running, undefined);
});
