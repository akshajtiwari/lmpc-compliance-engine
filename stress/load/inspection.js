import { check, sleep } from "k6";
import k6Crypto from "k6/crypto";
import encoding from "k6/encoding";
import http from "k6/http";
import { Rate, Trend } from "k6/metrics";

// A valid 96 x 64 white PNG. The listing text is the declaration evidence in this
// e-commerce flow; the screenshot still crosses the real evidence validation, immutable
// object-store and OCR boundaries.
const IMAGE = encoding.b64decode(
  "iVBORw0KGgoAAAANSUhEUgAAAGAAAABAAQAAAADNT0+jAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAAACYktHRAAB3YoTpAAAAAd0SU1FB+oJChI4JVqfD/MAAAAldEVYdGRhdGU6Y3JlYXRlADIwMjYtMDktMTBUMTg6NTY6MzcrMDA6MDDX5b2fAAAAJXRFWHRkYXRlOm1vZGlmeQAyMDI2LTA5LTEwVDE4OjU2OjM3KzAwOjAwprgFIwAAACh0RVh0ZGF0ZTp0aW1lc3RhbXAAMjAyNi0wOS0xMFQxODo1NjozNyswMDowMPGtJPwAAAAUSURBVCjPY/iPBBhGOaOcUQ4pHABsFf0ftgjPgQAAAABJRU5ErkJggg==",
);
const IMAGE_SHA256 = k6Crypto.sha256(IMAGE, "hex");

const BASE_URL = (__ENV.LMPC_LOAD_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const API = `${BASE_URL}/api/v1`;
const VUS = positiveInteger(__ENV.LMPC_LOAD_VUS, 2, "LMPC_LOAD_VUS");
const RAMP = __ENV.LMPC_LOAD_RAMP || "2s";
const HOLD = __ENV.LMPC_LOAD_HOLD || "15s";
const THINK_SECONDS = nonNegativeNumber(
  __ENV.LMPC_LOAD_THINK_SECONDS,
  0.25,
  "LMPC_LOAD_THINK_SECONDS",
);

const uploadDuration = new Trend("lmpc_upload_duration", true);
const verdictDuration = new Trend("lmpc_verdict_e2e_duration", true);
const repositoryDuration = new Trend("lmpc_repository_duration", true);
const flowFailures = new Rate("lmpc_inspection_flow_failed");

export const options = {
  scenarios: {
    inspection: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: RAMP, target: VUS },
        { duration: HOLD, target: VUS },
        { duration: RAMP, target: 0 },
      ],
      gracefulRampDown: "15s",
    },
  },
  thresholds: {
    checks: ["rate==1"],
    http_req_failed: ["rate==0"],
    lmpc_inspection_flow_failed: ["rate==0"],
    lmpc_upload_duration: ["p(95)<2000"],
    lmpc_verdict_e2e_duration: ["p(95)<15000", "p(99)<40000"],
    lmpc_repository_duration: ["p(95)<2000"],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
  userAgent: "LMPC-pilot-load-test/1.0",
};

export function setup() {
  const email = required("LMPC_LOAD_EMAIL");
  const password = required("LMPC_LOAD_PASSWORD");
  const ready = http.get(`${API}/readyz`, { tags: { operation: "readiness" } });
  const readinessOk = check(ready, {
    "server is ready before load": (response) =>
      response.status === 200 && response.json("status") === "ok",
  });
  if (!readinessOk) {
    throw new Error(`server readiness failed with HTTP ${ready.status}`);
  }

  const login = http.post(
    `${API}/auth/login`,
    JSON.stringify({ email, password }),
    {
      headers: { "Content-Type": "application/json" },
      tags: { operation: "login" },
      timeout: "10s",
    },
  );
  const loginOk = check(login, {
    "managed account signs in": (response) =>
      response.status === 200 && typeof response.json("access_token") === "string",
  });
  if (!loginOk) {
    throw new Error(`managed-account login failed with HTTP ${login.status}`);
  }
  return { accessToken: login.json("access_token") };
}

export default function (session) {
  const clientUuid = randomUuid();
  const headers = { Authorization: `Bearer ${session.accessToken}` };
  const flowStarted = Date.now();
  const create = http.post(
    `${API}/scans`,
    {
      client_uuid: clientUuid,
      captured_at: new Date().toISOString().slice(0, 10),
      mode: "ECOMMERCE_LISTING",
      category: "FOOD",
      coverage_asserted: "false",
      buyer_type: "RETAIL",
      package_shape: "RECTANGULAR",
      panels: "LISTING",
      image_sha256: IMAGE_SHA256,
      ecommerce: JSON.stringify({
        url: `https://load.example.test/products/${clientUuid}`,
        listing_text: "MRP Rs. 45.00 (incl. of all taxes)\nNet Qty 500 g",
      }),
      images: http.file(IMAGE, "listing.png", "image/png"),
    },
    {
      headers,
      tags: { operation: "upload" },
      timeout: "10s",
    },
  );
  uploadDuration.add(create.timings.duration);
  const created = check(create, {
    "scan upload is accepted": (response) => response.status === 202,
    "upload returns a scan id": (response) => isUuid(response.json("scan_id")),
  });
  if (!created) {
    if (__ITER === 0) {
      console.error(`upload failed with HTTP ${create.status}: ${String(create.body).slice(0, 500)}`);
    }
    flowFailures.add(true);
    sleep(THINK_SECONDS);
    return;
  }

  const scanId = create.json("scan_id");
  const process = http.post(`${API}/scans/${scanId}/process`, null, {
    headers,
    tags: { operation: "verdict" },
    timeout: "45s",
  });
  verdictDuration.add(Date.now() - flowStarted);
  const processed = check(process, {
    "analysis is accepted": (response) => response.status === 202,
    "analysis completes an evaluation": (response) =>
      response.json("status") === "EVALUATION_COMPLETE" &&
      Array.isArray(response.json("evaluations")) &&
      response.json("evaluations").length > 0,
  });
  if (!processed) {
    if (__ITER === 0) {
      console.error(`analysis failed with HTTP ${process.status}: ${String(process.body).slice(0, 500)}`);
    }
    flowFailures.add(true);
    sleep(THINK_SECONDS);
    return;
  }

  const detail = http.get(`${API}/scans/${scanId}`, {
    headers,
    tags: { operation: "repository" },
    timeout: "10s",
  });
  repositoryDuration.add(detail.timings.duration);
  const detailOk = check(detail, {
    "repository returns the evaluated scan": (response) =>
      response.status === 200 &&
      response.json("scan_id") === scanId &&
      response.json("status") === "EVALUATION_COMPLETE",
  });

  const search = http.get(`${API}/scans?q=${encodeURIComponent(clientUuid)}&page_size=5`, {
    headers,
    tags: { operation: "repository" },
    timeout: "10s",
  });
  repositoryDuration.add(search.timings.duration);
  const searchOk = check(search, {
    "repository search finds the submitted scan": (response) => {
      const items = response.json("items");
      return response.status === 200 &&
        Array.isArray(items) &&
        items.some((item) => item.id === scanId);
    },
  });

  const dashboard = http.get(`${API}/dashboard/summary`, {
    headers,
    tags: { operation: "repository" },
    timeout: "10s",
  });
  repositoryDuration.add(dashboard.timings.duration);
  const dashboardOk = check(dashboard, {
    "dashboard summary remains available": (response) => response.status === 200,
  });

  flowFailures.add(!(detailOk && searchOk && dashboardOk));
  sleep(THINK_SECONDS);
}

function required(name) {
  const value = (__ENV[name] || "").trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function positiveInteger(raw, fallback, name) {
  const value = raw === undefined || raw === "" ? fallback : Number(raw);
  if (!Number.isInteger(value) || value < 1) throw new Error(`${name} must be a positive integer`);
  return value;
}

function nonNegativeNumber(raw, fallback, name) {
  const value = raw === undefined || raw === "" ? fallback : Number(raw);
  if (!Number.isFinite(value) || value < 0) throw new Error(`${name} must be non-negative`);
  return value;
}

function isUuid(value) {
  return typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function randomUuid() {
  const bytes = new Uint8Array(k6Crypto.randomBytes(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const value = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${value.slice(0, 8)}-${value.slice(8, 12)}-${value.slice(12, 16)}-${value.slice(16, 20)}-${value.slice(20)}`;
}
