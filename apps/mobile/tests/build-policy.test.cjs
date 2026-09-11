const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");

const plugin = require("../plugins/with-local-http.js");

function manifestWith(attributes) {
  return {manifest: {application: [{$: attributes}]}};
}

test("cleartext is denied unless the preview environment is set", () => {
  assert.equal(plugin.previewCleartextAllowed({}), false);
  assert.equal(plugin.previewCleartextAllowed({LMPC_FIELD_PREVIEW_HTTP: "0"}), false);
  assert.equal(plugin.previewCleartextAllowed({LMPC_FIELD_PREVIEW_HTTP: "1"}), true);
});

test("default manifest keeps Android's cleartext denial", () => {
  const manifest = plugin.applyNetworkPolicy(
    manifestWith({"android:usesCleartextTraffic": "true"}),
    false,
  );
  const attributes = manifest.manifest.application[0].$;
  assert.ok(!("android:usesCleartextTraffic" in attributes));
  assert.ok(!("android:networkSecurityConfig" in attributes));
});

test("preview manifest points at a scoped network security config", () => {
  const manifest = plugin.applyNetworkPolicy(manifestWith({}), true);
  const attributes = manifest.manifest.application[0].$;
  assert.ok(!("android:usesCleartextTraffic" in attributes));
  assert.match(attributes["android:networkSecurityConfig"], /^@xml\//);
});

test("preview network security config is explicitly labeled", () => {
  assert.match(plugin.previewNetworkSecurityXml(), /cleartextTrafficPermitted="true"/);
  assert.match(plugin.previewNetworkSecurityXml(), /preview/);
});

test("app.json never permits arbitrary iOS loads", () => {
  const config = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "app.json"), "utf8"));
  const ats = config.expo.ios.infoPlist.NSAppTransportSecurity ?? {};
  assert.ok(!("NSAllowsArbitraryLoads" in ats));
});

test("preview release workflow is the only place the preview env is set", () => {
  const workflows = path.join(__dirname, "..", "..", "..", ".github", "workflows");
  const files = fs.readdirSync(workflows).filter((name) => name.endsWith(".yml"));
  const setting = files.filter((name) =>
    fs.readFileSync(path.join(workflows, name), "utf8").includes("LMPC_FIELD_PREVIEW_HTTP"),
  );
  assert.deepEqual(setting, ["mobile-preview-release.yml"]);
});