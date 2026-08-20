import assert from "node:assert/strict";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  discoverAndLoadExtensions,
  loadSkillsFromDir,
} from "@earendil-works/pi-coding-agent";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

test("Pi discovers the package extension and skill from the root manifest", async () => {
  const loaded = await discoverAndLoadExtensions([packageRoot], packageRoot);
  assert.deepEqual(loaded.errors, []);
  assert.equal(loaded.extensions.length, 1);
  assert.deepEqual([...loaded.extensions[0].tools.keys()], [
    "submit_read_query",
    "get_query_status",
  ]);

  const loadedSkills = loadSkillsFromDir({
    dir: resolve(packageRoot, "integrations/pi/skills"),
    source: "snowglobe-package-smoke-test",
  });
  assert.deepEqual(loadedSkills.diagnostics, []);
  assert.deepEqual(loadedSkills.skills.map((skill) => skill.name), ["snowglobe"]);
});
