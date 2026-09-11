import jpeg from "jpeg-js";

// Client-side frame gate (plan §6.2 step 4). Measurements run on a downscaled copy
// of every frame before it can be attached to an inspection; the server rechecks and
// records them, but never trusts them for a verdict. Thresholds are deliberately
// conservative: the gate must reject clearly unusable frames without blocking
// legitimate ones on unprofiled devices.
export const QUALITY_THRESHOLDS = {
  minSharpness: 25,
  darkMeanLuma: 55,
  brightMeanLuma: 205,
  glareLuma: 248,
  maxGlareFraction: 0.06,
} as const;

export type FrameQuality = {
  source: "CAMERA" | "GALLERY";
  sharpness: number;
  mean_luma: number;
  glare_fraction: number;
  warnings: string[];
};

export type GrayFrame = {data: Uint8Array; width: number; height: number};

export function decodeBase64(value: string): Uint8Array {
  const table = BASE64_TABLE;
  const clean = value.replace(/[^A-Za-z0-9+/=]/g, "");
  const length = clean.length;
  const padding = clean.endsWith("==") ? 2 : clean.endsWith("=") ? 1 : 0;
  const out = new Uint8Array(Math.max(0, Math.floor(length / 4) * 3 - padding));
  let buffer = 0;
  let bits = 0;
  let cursor = 0;
  for (let index = 0; index < length; index++) {
    const code = table[clean[index]];
    if (code === undefined) continue;
    buffer = (buffer << 6) | code;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out[cursor++] = (buffer >> bits) & 0xff;
    }
  }
  return out;
}

export function decodeJpeg(bytes: Uint8Array): GrayFrame {
  const decoded = jpeg.decode(bytes, {useTArray: true, formatAsRGBA: true});
  const {width, height} = decoded;
  const gray = new Uint8Array(width * height);
  for (let index = 0; index < gray.length; index++) {
    const offset = index * 4;
    gray[index] = (decoded.data[offset] + decoded.data[offset + 1] + decoded.data[offset + 2]) / 3 | 0;
  }
  return {data: gray, width, height};
}

// Variance of the Laplacian over 0..255 luminance: near zero for a flat (blurred)
// frame, large when character edges are crisp.
export function laplacianVariance(frame: GrayFrame): number {
  const {data, width, height} = frame;
  if (width < 3 || height < 3) return 0;
  let sum = 0;
  let sumSquares = 0;
  let count = 0;
  for (let y = 1; y < height - 1; y++) {
    const row = y * width;
    for (let x = 1; x < width - 1; x++) {
      const at = row + x;
      const response = 4 * data[at] - data[at - 1] - data[at + 1]
        - data[at - width] - data[at + width];
      sum += response;
      sumSquares += response * response;
      count++;
    }
  }
  if (!count) return 0;
  const mean = sum / count;
  return sumSquares / count - mean * mean;
}

export function meanLuma(frame: GrayFrame): number {
  let total = 0;
  for (let index = 0; index < frame.data.length; index++) total += frame.data[index];
  return total / Math.max(1, frame.data.length);
}

export function glareFraction(frame: GrayFrame, glareLuma: number): number {
  let bright = 0;
  for (let index = 0; index < frame.data.length; index++) {
    if (frame.data[index] >= glareLuma) bright++;
  }
  return bright / Math.max(1, frame.data.length);
}

export function analyzeFrame(frame: GrayFrame, source: FrameQuality["source"]): FrameQuality {
  const sharpness = laplacianVariance(frame);
  const luma = meanLuma(frame);
  const glare = glareFraction(frame, QUALITY_THRESHOLDS.glareLuma);
  const warnings: string[] = [];
  if (sharpness < QUALITY_THRESHOLDS.minSharpness) warnings.push("blur");
  if (luma < QUALITY_THRESHOLDS.darkMeanLuma) warnings.push("dark");
  if (luma > QUALITY_THRESHOLDS.brightMeanLuma) warnings.push("bright");
  if (glare > QUALITY_THRESHOLDS.maxGlareFraction) warnings.push("glare");
  return {source, sharpness, mean_luma: luma, glare_fraction: glare, warnings};
}

// Plain-language correction for each rejected frame (plan §6.2 step 4).
export function qualityMessages(warnings: string[]): string[] {
  const messages: string[] = [];
  if (warnings.includes("blur")) messages.push("The photo is blurred. Hold the phone steady and retake.");
  if (warnings.includes("dark")) messages.push("The photo is too dark. Move to better light or retake.");
  if (warnings.includes("bright")) messages.push("The photo is washed out. Retake away from direct light.");
  if (warnings.includes("glare")) messages.push("Heavy glare covers the label. Angle the package away from the light and retake.");
  return messages;
}

export function gateAccepted(quality: FrameQuality): boolean {
  return quality.warnings.length === 0;
}

const BASE64_TABLE = (() => {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const table: Record<string, number> = {};
  for (let index = 0; index < alphabet.length; index++) table[alphabet[index]] = index;
  return table;
})();