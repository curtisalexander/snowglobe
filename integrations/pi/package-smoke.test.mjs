import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { discoverAndLoadExtensions } from "@earendil-works/pi-coding-agent";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

test("Pi discovers the package extension from the root manifest", async () => {
  const loaded = await discoverAndLoadExtensions([packageRoot], packageRoot);
  assert.deepEqual(loaded.errors, []);
  assert.equal(loaded.extensions.length, 1);
  assert.deepEqual([...loaded.extensions[0].tools.keys()], [
    "submit_read_query",
    "get_query_status",
  ]);
});

test("the installable package contains only its runtime", () => {
  const npmCli = process.env.npm_execpath;
  assert.ok(npmCli, "npm_execpath is required to inspect the package");
  const packed = JSON.parse(
    execFileSync(
      process.execPath,
      [npmCli, "pack", "--dry-run", "--json", "--ignore-scripts"],
      {
        cwd: packageRoot,
        encoding: "utf8",
      },
    ),
  );
  const files = new Set(packed[0].files.map((file) => file.path));

  for (const required of [
    "integrations/pi/extensions/contracts.ts",
    "integrations/pi/extensions/index.ts",
    "integrations/pi/extensions/process.ts",
    "src/snowglobe/cli.py",
    "pyproject.toml",
    "uv.lock",
  ]) {
    assert.ok(files.has(required), `missing package runtime file: ${required}`);
  }
  assert.ok(
    [...files].every(
      (file) =>
        !file.startsWith("apps/") &&
        !file.startsWith("docs/") &&
        !file.startsWith("tests/") &&
        !file.startsWith(".agents/") &&
        !file.includes("__pycache__") &&
        !file.endsWith(".pyc"),
    ),
  );
});
