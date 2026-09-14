const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const workflowPath = path.resolve(
  __dirname, "../../../.github/workflows/mobile-preview-release.yml");
const workflow = readFileSync(workflowPath, "utf8");

test("published Android preview is a standalone release bundle", () => {
  assert.match(workflow, /\.\/gradlew assembleRelease --no-daemon/);
  assert.doesNotMatch(workflow, /\.\/gradlew assembleDebug/);
  assert.match(workflow, /outputs\/apk\/release\/app-release\.apk/);
  assert.match(workflow, /assets\/index\.android\.bundle/);
});
