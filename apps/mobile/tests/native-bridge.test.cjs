/* Guards against passing types the Expo native bridge cannot convert.

   These do not fail typecheck and do not fail in any test that stops at the JS boundary.
   They fail on a device, at the moment an officer is standing in front of a shelf.

   The one that shipped: `digest(SHA256, await file.arrayBuffer())`. expo-crypto types
   `data` as `BufferSource`, which includes ArrayBuffer, so TypeScript was satisfied.
   On Android the Kotlin bridge threw

     [digest] Cannot convert '[object ArrayBuffer]' to a Kotlin type. no ArrayBuffer attached

   and because every panel upload hashes its image first, no scan could ever be uploaded.
   `File.bytes()` returns a Uint8Array, which the bridge does convert.

   The one hiding behind it: `formData.append("image", {uri, name, type})`, React Native's
   legacy file shorthand. Expo's WinterCG fetch builds the multipart body in JS and takes
   only a string, a Blob, or something with a bytes() method
   (expo/src/winter/fetch/convertFormData.ts, which states "uri is not supported"), so it
   threw "Unsupported FormDataPart implementation". Both were cast through
   `as unknown as Blob`, which is exactly what stopped the compiler noticing. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = path.join(__dirname, "..", "src");

function sources() {
  return fs.readdirSync(SOURCE, {recursive: true})
    .filter((name) => typeof name === "string" && /\.tsx?$/.test(name))
    .map((name) => ({name, text: fs.readFileSync(path.join(SOURCE, name), "utf8")}));
}

test("no ArrayBuffer is handed to a native module", () => {
  const offenders = [];
  for (const {name, text} of sources()) {
    // `digest(...)`/`digestStringAsync(...)` and friends reading a whole file: the
    // argument must be bytes(), never arrayBuffer().
    for (const match of text.matchAll(/digest\s*\([^)]*arrayBuffer\s*\(\s*\)/g)) {
      offenders.push(`${name}: ${match[0].slice(0, 80)}`);
    }
  }
  assert.deepEqual(offenders, [],
    "pass File.bytes() (Uint8Array) to expo-crypto, not File.arrayBuffer()");
});

test("the panel hash still reads the file as bytes", () => {
  const api = fs.readFileSync(path.join(SOURCE, "api.ts"), "utf8");
  assert.match(api, /digest\(CryptoDigestAlgorithm\.SHA256,\s*await file\.bytes\(\)\)/,
    "sha256() must hash File.bytes(); an ArrayBuffer breaks every upload on Android");
});

test("no FormData part uses React Native's legacy {uri,name,type} shorthand", () => {
  const offenders = [];
  for (const {name, text} of sources()) {
    for (const match of text.matchAll(/\.append\s*\([^)]*\buri\s*:/g)) {
      offenders.push(`${name}: ${match[0].slice(0, 80)}`);
    }
  }
  assert.deepEqual(offenders, [],
    "append the expo-file-system File itself; Expo's fetch rejects a {uri} part");
});

test("the panel image is sent as a File the converter understands", () => {
  const api = fs.readFileSync(path.join(SOURCE, "api.ts"), "utf8");
  assert.match(api, /panelForm\.append\("image",\s*file as unknown as Blob\)/,
    "the image part must be the File object, which carries bytes(), name and type");
});

test("every image upload sends a hash the server will check", () => {
  const api = fs.readFileSync(path.join(SOURCE, "api.ts"), "utf8");
  assert.ok(api.includes('panelForm.append("image_sha256",await sha256(file))'),
    "the server rejects a panel whose declared sha256 does not match the bytes");
});
