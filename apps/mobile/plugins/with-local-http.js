const fs = require("fs");
const path = require("path");
const {withAndroidManifest, withDangerousMod} = require("expo/config-plugins");

// Cleartext HTTP is permitted only for the labeled LAN preview profile. The release
// workflow sets LMPC_FIELD_PREVIEW_HTTP=1; every other build (including any future
// production profile) keeps the Android default, which denies cleartext traffic.
const PREVIEW_HTTP_ENV = "LMPC_FIELD_PREVIEW_HTTP";
const RESOURCE_NAME = "lmpc_preview_network_security_config";

function previewCleartextAllowed(env = process.env) {
  return env[PREVIEW_HTTP_ENV] === "1";
}

function previewNetworkSecurityXml() {
  return `<?xml version="1.0" encoding="utf-8"?>
<!-- LMPC Field LAN preview: permits cleartext only in the labeled preview profile. -->
<network-security-config>
    <base-config cleartextTrafficPermitted="true" />
</network-security-config>
`;
}

function applyNetworkPolicy(manifest, allowPreviewCleartext) {
  const application = manifest.manifest?.application?.[0];
  if (!application) return manifest;
  delete application.$["android:usesCleartextTraffic"];
  if (allowPreviewCleartext) {
    application.$["android:networkSecurityConfig"] = `@xml/${RESOURCE_NAME}`;
  } else {
    delete application.$["android:networkSecurityConfig"];
  }
  return manifest;
}

function writeNetworkSecurityConfig(platformProjectRoot) {
  const dir = path.join(platformProjectRoot, "app", "src", "main", "res", "xml");
  fs.mkdirSync(dir, {recursive: true});
  fs.writeFileSync(path.join(dir, `${RESOURCE_NAME}.xml`), previewNetworkSecurityXml());
}

module.exports = function withLocalHttp(config) {
  const allowed = previewCleartextAllowed();
  config = withAndroidManifest(config, (next) => {
    applyNetworkPolicy(next.modResults, allowed);
    return next;
  });
  if (allowed) {
    config = withDangerousMod(config, ["android", (next) => {
      writeNetworkSecurityConfig(next.modRequest.platformProjectRoot);
      return next;
    }]);
  }
  return config;
};

module.exports.PREVIEW_HTTP_ENV = PREVIEW_HTTP_ENV;
module.exports.previewCleartextAllowed = previewCleartextAllowed;
module.exports.applyNetworkPolicy = applyNetworkPolicy;
module.exports.previewNetworkSecurityXml = previewNetworkSecurityXml;
module.exports.writeNetworkSecurityConfig = writeNetworkSecurityConfig;