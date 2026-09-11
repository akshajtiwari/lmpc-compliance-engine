const test = require("node:test");
const assert = require("node:assert/strict");

const {analyzeFrame, qualityMessages, gateAccepted, decodeBase64, decodeJpeg,
  laplacianVariance} = require("../.test-dist/quality.js");

function solidFrame(width, height, value) {
  return {data: new Uint8Array(width * height).fill(value), width, height};
}

function checkerboard(width, height, period = 2) {
  const data = new Uint8Array(width * height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      data[y * width + x] = (Math.floor(x / period) + Math.floor(y / period)) % 2 ? 240 : 10;
    }
  }
  return {data, width, height};
}

function withGlareSpot(frame) {
  const data = Uint8Array.from(frame.data);
  const {width} = frame;
  for (let y = 10; y < 30; y++) {
    for (let x = 10; x < 30; x++) data[y * width + x] = 255;
  }
  return {data, width: frame.width, height: frame.height};
}

test("a flat frame is blurred and rejected with plain-language advice", () => {
  const quality = analyzeFrame(solidFrame(64, 64, 128), "CAMERA");
  assert.equal(quality.sharpness, 0);
  assert.deepEqual(quality.warnings, ["blur"]);
  assert.equal(gateAccepted(quality), false);
  assert.deepEqual(qualityMessages(quality.warnings),
    ["The photo is blurred. Hold the phone steady and retake."]);
});

test("a crisp frame passes the gate with no warnings", () => {
  const quality = analyzeFrame(checkerboard(64, 64), "CAMERA");
  assert.ok(quality.sharpness > 25);
  assert.deepEqual(quality.warnings, []);
  assert.equal(gateAccepted(quality), true);
  assert.deepEqual(qualityMessages(quality.warnings), []);
});

test("dark and bright frames are reported as exposure problems", () => {
  const dark = analyzeFrame(solidFrame(64, 64, 20), "CAMERA");
  const bright = analyzeFrame(solidFrame(64, 64, 240), "CAMERA");
  assert.ok(dark.warnings.includes("dark"));
  assert.ok(bright.warnings.includes("bright"));
  const messages = qualityMessages(bright.warnings).join(" ");
  assert.match(messages, /washed out/);
});

test("a glare hotspot raises the glare warning", () => {
  const frame = withGlareSpot(solidFrame(64, 64, 100));
  const quality = analyzeFrame(frame, "CAMERA");
  assert.ok(quality.glare_fraction > 0.06);
  assert.ok(quality.warnings.includes("glare"));
});

test("gallery evidence is recorded with its source", () => {
  const quality = analyzeFrame(checkerboard(32, 32), "GALLERY");
  assert.equal(quality.source, "GALLERY");
});

test("tiny frames measure as unusable rather than crashing", () => {
  assert.equal(laplacianVariance({data: new Uint8Array(5), width: 5, height: 1}), 0);
});

test("base64 decoding round-trips binary data", () => {
  const bytes = new Uint8Array(256);
  for (let index = 0; index < bytes.length; index++) bytes[index] = index;
  const encoded = Buffer.from(bytes).toString("base64");
  assert.deepEqual(decodeBase64(encoded), bytes);
});

test("base64 decoding handles padding and whitespace", () => {
  const encoded = Buffer.from([1, 2, 3, 4]).toString("base64");
  assert.deepEqual(decodeBase64(`${encoded}\n`), new Uint8Array([1, 2, 3, 4]));
});

test("a real JPEG decodes to measurable gray pixels", () => {
  const frame = decodeJpeg(minimalGrayJpeg());
  assert.equal(frame.width, 8);
  assert.equal(frame.height, 8);
  const quality = analyzeFrame(frame, "CAMERA");
  assert.ok(quality.mean_luma > 100 && quality.mean_luma < 160);
  assert.ok(quality.warnings.includes("blur"));
});

function minimalGrayJpeg() {
  // Build an 8x8 gray JPEG with jpeg-js itself so the decoder is exercised honestly.
  const jpeg = require("jpeg-js");
  const data = Buffer.alloc(8 * 8 * 4);
  for (let index = 0; index < data.length; index += 4) {
    data[index] = data[index + 1] = data[index + 2] = 130;
    data[index + 3] = 255;
  }
  return jpeg.encode({data, width: 8, height: 8}, 90).data;
}