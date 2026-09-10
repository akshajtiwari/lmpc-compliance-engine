const API = "/api/v1";
const DB_NAME = "lmpc-field-v1";
const DB_VERSION = 1;
const REQUIRED_FREE_BYTES = 200 * 1024 * 1024;
const MAX_UPLOAD_EDGE = 2400;
const PANELS = [
  {id: "FRONT", title: "Front panel", kind: "REQUIRED PANEL", required: true,
   instruction: "Place the principal display panel inside the guide. Keep the camera square and make all print readable."},
  {id: "BACK", title: "Back panel", kind: "REQUIRED PANEL", required: true,
   instruction: "Capture the entire rear panel, including consumer-care and manufacturer declarations."},
  {id: "SIDE_1", title: "First side", kind: "OPTIONAL PANEL", required: false,
   instruction: "Capture this side when any declaration or continuation of text appears here."},
  {id: "SIDE_2", title: "Second side", kind: "OPTIONAL PANEL", required: false,
   instruction: "Capture the remaining side when it contains printed or moulded declarations."},
  {id: "SCALE_REF", title: "Scale reference", kind: "MEASUREMENT AID", required: false,
   instruction: "Keep the reference coplanar with the label. It must not sit in front of or behind the measured panel."},
];
const LISTING_PANEL = {id: "LISTING", title: "Product listing", kind: "LISTING EVIDENCE", required: true,
  instruction: "Capture the product page with the title, price and visible declarations. Paste listing text in the previous step."};
const OUTCOMES = {
  FAIL: ["✕", "Violation"], REVIEW_REQUIRED: ["!", "Needs review"],
  INDETERMINATE: ["?", "Cannot determine"], SYSTEM_ERROR: ["⚠", "System error"],
  PASS: ["✓", "Compliant"], NOT_APPLICABLE: ["–", "Not applicable"],
};
const RETRY_DELAYS = [5000, 15000, 60000, 300000, 1800000, 3600000];

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[char]);
const titleCase = (value) => String(value || "").toLowerCase().replaceAll("_", " ")
  .replace(/\b\w/g, letter => letter.toUpperCase());
const today = () => {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};

let dbPromise;
let draft = freshDraft();
let panelIndex = 0;
let stream = null;
let liveTimer = null;
let analysingLive = false;
let selectedOutcome = "ALL";
let selectedEvidence = "";

function freshDraft() {
  return {
    client_uuid: crypto.randomUUID(), captured_at: today(), mode: "PHYSICAL_PACKAGE",
    category: "FOOD", buyer_type: "RETAIL", package_shape: "RECTANGULAR",
    scale_type: "NONE", h_cm: null, w_cm: null, is_imported: false,
    is_molded: false, listing_url: "", listing_text: "", frames: {}, waived: {},
    status: "DRAFT", created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    server_result: null, report: null,
  };
}

function activePanels() {
  return draft.mode === "ECOMMERCE_LISTING" ? [LISTING_PANEL] : PANELS;
}

function openDb() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("scans")) db.createObjectStore("scans", {keyPath: "client_uuid"});
      if (!db.objectStoreNames.contains("images")) {
        const images = db.createObjectStore("images", {keyPath: "id"});
        images.createIndex("client_uuid", "client_uuid");
      }
      if (!db.objectStoreNames.contains("outbox")) db.createObjectStore("outbox", {keyPath: "client_uuid"});
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  return dbPromise;
}

async function idb(storeName, mode, operation) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, mode);
    const store = tx.objectStore(storeName);
    const request = operation(store);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
const dbPut = (store, value) => idb(store, "readwrite", target => target.put(value));
const dbGet = (store, key) => idb(store, "readonly", target => target.get(key));
const dbAll = (store) => idb(store, "readonly", target => target.getAll());
const dbDelete = (store, key) => idb(store, "readwrite", target => target.delete(key));

function serialDraft(value) {
  const {frames, ...plain} = value;
  plain.frame_panels = Object.keys(frames);
  return plain;
}

async function persistDraft(value = draft) {
  value.updated_at = new Date().toISOString();
  await dbPut("scans", serialDraft(value));
  for (const [panel, frame] of Object.entries(value.frames)) {
    await dbPut("images", {
      id: `${value.client_uuid}:${panel}`, client_uuid: value.client_uuid, panel,
      blob: frame.blob, type: frame.type, name: frame.name, source: frame.source,
      quality: frame.quality, sha256: frame.sha256 || "",
    });
  }
  await refreshQueueCount();
}

async function hydrateDraft(row) {
  const images = (await dbAll("images")).filter(item => item.client_uuid === row.client_uuid);
  const frames = {};
  for (const image of images) {
    frames[image.panel] = {...image, preview: URL.createObjectURL(image.blob)};
  }
  return {...row, frames, waived: row.waived || {}};
}

function releasePreviews(value = draft) {
  Object.values(value.frames || {}).forEach(frame => {
    if (frame.preview) URL.revokeObjectURL(frame.preview);
  });
}

function showView(id) {
  stopCamera();
  $$(".view").forEach(view => view.classList.toggle("active", view.id === id));
  window.scrollTo({top: 0, behavior: "auto"});
  $(`#${id}`)?.focus?.();
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 3500);
}

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  const type = response.headers.get("content-type") || "";
  const body = type.includes("json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = body?.error?.message || body || `Request failed (${response.status})`;
    const error = new Error(message);
    error.code = body?.error?.code;
    error.status = response.status;
    throw error;
  }
  return body;
}

async function checkService() {
  const dot = $("#serviceDot");
  try {
    const ready = await request("/readyz", {cache: "no-store"});
    dot.className = "ok";
    $("#serviceStatus").textContent = "Ready on this machine";
    $("#serviceDetail").textContent = ready.status === "ok" ?
      "Rulepack, database and local evidence store verified" : "A dependency is unavailable";
  } catch (error) {
    dot.className = "bad";
    $("#serviceStatus").textContent = navigator.onLine ? "Local service unavailable" : "You are offline";
    $("#serviceDetail").textContent = navigator.onLine ? "Start it with make dev" : "Captures can still be queued on this device";
  }
}

function updateNetwork() {
  const online = navigator.onLine;
  $("#networkState").className = `network ${online ? "online" : "offline"}`;
  $("#networkState span").textContent = online ? "Connected" : "Offline";
  checkService();
}

async function checkStorage() {
  if (!navigator.storage?.estimate) {
    $("#storageStatus").textContent = "Offline storage is available";
    return true;
  }
  const estimate = await navigator.storage.estimate();
  const remaining = (estimate.quota || 0) - (estimate.usage || 0);
  const mb = Math.max(0, Math.floor(remaining / 1024 / 1024));
  $("#storageStatus").textContent = `${mb.toLocaleString()} MB available for offline evidence`;
  $("#newScanButton").disabled = remaining > 0 && remaining < REQUIRED_FREE_BYTES;
  return remaining === 0 || remaining >= REQUIRED_FREE_BYTES;
}

async function refreshQueueCount() {
  const queued = await dbAll("outbox");
  $("#queuedCount").textContent = queued.length;
}

function beginScan() {
  releasePreviews();
  draft = freshDraft();
  panelIndex = 0;
  $("#setupForm").reset();
  $("#dateInput").value = draft.captured_at;
  $("#listingFields").hidden = true;
  showView("setupView");
}

async function discardCurrent() {
  if (!window.confirm("Discard this draft and its photographs from this device?")) return;
  const id = draft.client_uuid;
  releasePreviews();
  for (const image of (await dbAll("images")).filter(item => item.client_uuid === id)) {
    await dbDelete("images", image.id);
  }
  await Promise.all([dbDelete("scans", id), dbDelete("outbox", id)]);
  await refreshQueueCount();
  draft = freshDraft();
  showView("homeView");
  toast("Draft discarded from this device.");
}

function readSetup(form) {
  const data = new FormData(form);
  const number = name => data.get(name) ? Number(data.get(name)) : null;
  Object.assign(draft, {
    mode: data.get("mode"), category: data.get("category"), buyer_type: data.get("buyer_type"),
    package_shape: data.get("package_shape"), captured_at: data.get("captured_at"),
    scale_type: data.get("scale_type"), h_cm: number("h_cm"), w_cm: number("w_cm"),
    is_imported: data.has("is_imported"), is_molded: data.has("is_molded"),
    listing_url: data.get("listing_url") || "", listing_text: data.get("listing_text") || "",
  });
  if ((draft.h_cm === null) !== (draft.w_cm === null)) throw new Error("Enter both panel height and width, or leave both empty.");
  if (draft.mode === "ECOMMERCE_LISTING" && !draft.listing_text.trim()) throw new Error("Paste the visible listing text for an e-commerce inspection.");
}

function renderCapture() {
  const panels = activePanels();
  panelIndex = Math.max(0, Math.min(panelIndex, panels.length - 1));
  const panel = panels[panelIndex];
  $("#stepText").textContent = `Panel ${panelIndex + 1} of ${panels.length}`;
  $("#stepProgress").style.width = `${((panelIndex + 1) / panels.length) * 100}%`;
  $("#panelKind").textContent = panel.kind;
  $("#captureTitle").textContent = panel.title;
  $("#panelInstruction").textContent = panel.instruction;
  $("#qualityMessage").hidden = true;
  resetQuality();
  const frame = draft.frames[panel.id];
  $("#acceptedPreview").hidden = !frame;
  if (frame) {
    $("#acceptedImage").src = frame.preview;
    $("#acceptedMetrics").textContent = qualityLine(frame.quality);
    paintQuality(frame.quality);
  }
  const waivable = panel.id !== "FRONT" && panel.id !== "LISTING";
  $("#waiveBox").hidden = !waivable;
  $("#waiveTitle").textContent = panel.required ? "This required panel is unavailable" : "Skip this optional panel";
  $("#waiveHelp").textContent = panel.required ?
    "Coverage will not be asserted. Missing declarations will remain indeterminate." :
    "Optional panels do not affect the coverage assertion.";
  $("#waiveInput").checked = Boolean(draft.waived[panel.id]);
  $("#nextPanelButton").disabled = !frame && !draft.waived[panel.id];
  $("#nextPanelButton").textContent = panelIndex === panels.length - 1 ? "Review evidence →" : "Accept and continue →";
  showView("captureView");
}

function resetQuality() {
  $$("#qualityList > div").forEach(row => {
    row.className = "";
    row.querySelector("i").textContent = "○";
    row.querySelector("b").textContent = "Waiting";
  });
}

function gateValues(quality) {
  return {
    resolution: {pass: quality.long_edge >= 1200, value: `${quality.long_edge} px`},
    blur: {pass: quality.blur >= 100, value: quality.blur.toFixed(0)},
    exposure: {pass: quality.luma >= 40 && quality.luma <= 215, value: quality.luma.toFixed(0)},
    glare: {pass: quality.glare <= .03, value: `${(quality.glare * 100).toFixed(1)}%`},
  };
}

function paintQuality(quality) {
  for (const [name, gate] of Object.entries(gateValues(quality))) {
    const row = $(`#qualityList [data-gate="${name}"]`);
    row.className = gate.pass ? "pass" : "fail";
    row.querySelector("i").textContent = gate.pass ? "✓" : "×";
    row.querySelector("b").textContent = gate.value;
  }
}

function qualityLine(quality) {
  return `${quality.width}×${quality.height} · sharpness ${quality.blur.toFixed(0)} · glare ${(quality.glare * 100).toFixed(1)}%`;
}

function rejection(quality) {
  const gates = gateValues(quality);
  if (!gates.resolution.pass) return "Move closer — the long edge must be at least 1200 pixels.";
  if (!gates.blur.pass) return "Too blurry — hold still and focus on the printed declarations.";
  if (quality.luma < 40) return "Too dark — add light without casting a shadow on the panel.";
  if (quality.luma > 215) return "Too bright — reduce direct light on the panel.";
  if (!gates.glare.pass) return "Glare detected — tilt the package away from direct light.";
  return "";
}

function analysePixels(canvas, originalWidth, originalHeight) {
  const max = 420;
  const ratio = Math.min(1, max / Math.max(canvas.width, canvas.height));
  const work = document.createElement("canvas");
  work.width = Math.max(2, Math.round(canvas.width * ratio));
  work.height = Math.max(2, Math.round(canvas.height * ratio));
  const context = work.getContext("2d", {willReadFrequently: true});
  context.drawImage(canvas, 0, 0, work.width, work.height);
  const pixels = context.getImageData(0, 0, work.width, work.height).data;
  let lumaTotal = 0, glare = 0, lapTotal = 0, lapSquared = 0, lapCount = 0;
  const width = work.width;
  const green = index => pixels[index * 4 + 1];
  for (let i = 0; i < pixels.length; i += 4) {
    const y = .2126 * pixels[i] + .7152 * pixels[i + 1] + .0722 * pixels[i + 2];
    lumaTotal += y;
    if (y > 250) glare += 1;
  }
  for (let y = 1; y < work.height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const at = y * width + x;
      const lap = 4 * green(at) - green(at - 1) - green(at + 1) - green(at - width) - green(at + width);
      lapTotal += lap; lapSquared += lap * lap; lapCount += 1;
    }
  }
  const lapMean = lapTotal / Math.max(1, lapCount);
  return {
    width: originalWidth, height: originalHeight, long_edge: Math.max(originalWidth, originalHeight),
    luma: lumaTotal / (pixels.length / 4), glare: glare / (pixels.length / 4),
    blur: Math.max(0, lapSquared / Math.max(1, lapCount) - lapMean * lapMean),
  };
}

async function processFile(file, source) {
  let bitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error("This browser could not decode that image. Use a JPEG or PNG photograph.");
  }
  const ratio = Math.min(1, MAX_UPLOAD_EDGE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * ratio);
  canvas.height = Math.round(bitmap.height * ratio);
  const context = canvas.getContext("2d", {alpha: false, willReadFrequently: true});
  context.fillStyle = "#fff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const quality = analysePixels(canvas, bitmap.width, bitmap.height);
  bitmap.close();
  paintQuality(quality);
  const problem = rejection(quality);
  if (problem) {
    $("#qualityMessage").textContent = problem;
    $("#qualityMessage").hidden = false;
    throw new Error(problem);
  }
  const blob = await new Promise((resolve, reject) => canvas.toBlob(
    value => value ? resolve(value) : reject(new Error("Could not prepare the photograph.")), "image/jpeg", .85));
  await acceptFrame(blob, file.name || `${activePanels()[panelIndex].id}.jpg`, source, quality);
}

async function acceptFrame(blob, name, source, quality) {
  const panel = activePanels()[panelIndex].id;
  const prior = draft.frames[panel];
  if (prior?.preview) URL.revokeObjectURL(prior.preview);
  draft.frames[panel] = {blob, name, type: "image/jpeg", source, quality, preview: URL.createObjectURL(blob)};
  delete draft.waived[panel];
  $("#waiveInput").checked = false;
  $("#acceptedPreview").hidden = false;
  $("#acceptedImage").src = draft.frames[panel].preview;
  $("#acceptedMetrics").textContent = qualityLine(quality);
  $("#nextPanelButton").disabled = false;
  $("#qualityMessage").hidden = true;
  await persistDraft();
  toast("Panel passed all measurable quality gates.");
}

async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    toast("Camera access is unavailable here. Choose a photograph instead.");
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: {facingMode: {ideal: "environment"}, width: {ideal: 3840}, height: {ideal: 2160},
        focusMode: {ideal: "continuous"}}, audio: false,
    });
    const video = $("#camera");
    video.srcObject = stream;
    await video.play();
    $("#cameraShell").classList.add("active");
    $("#shutterButton").hidden = false;
    $("#startCameraButton").textContent = "Camera active";
    $("#startCameraButton").disabled = true;
    $("#liveQuality").hidden = false;
    liveTimer = setInterval(analysePreview, 200);
  } catch (error) {
    toast(error.name === "NotAllowedError" ? "Camera permission was denied. Choose a photograph instead." : "The camera could not be started.");
  }
}

function stopCamera() {
  if (liveTimer) clearInterval(liveTimer);
  liveTimer = null;
  stream?.getTracks().forEach(track => track.stop());
  stream = null;
  const video = $("#camera");
  if (video) video.srcObject = null;
  $("#cameraShell")?.classList.remove("active");
  if ($("#shutterButton")) $("#shutterButton").hidden = true;
  if ($("#startCameraButton")) { $("#startCameraButton").disabled = false; $("#startCameraButton").textContent = "Start camera"; }
}

function analysePreview() {
  const video = $("#camera");
  if (analysingLive || !video.videoWidth) return;
  analysingLive = true;
  try {
    const canvas = $("#captureCanvas");
    const ratio = Math.min(1, 360 / Math.max(video.videoWidth, video.videoHeight));
    canvas.width = Math.round(video.videoWidth * ratio);
    canvas.height = Math.round(video.videoHeight * ratio);
    canvas.getContext("2d", {willReadFrequently: true}).drawImage(video, 0, 0, canvas.width, canvas.height);
    const quality = analysePixels(canvas, video.videoWidth, video.videoHeight);
    paintQuality(quality);
    $("#liveQuality").textContent = rejection(quality) || "Quality gates ready";
  } finally {
    analysingLive = false;
  }
}

async function captureCameraFrame() {
  const video = $("#camera");
  if (!video.videoWidth) return;
  const canvas = $("#captureCanvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d", {alpha: false}).drawImage(video, 0, 0);
  const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", .92));
  if (!blob) return;
  try { await processFile(blob, "camera"); } catch (error) { toast(error.message); }
}

async function nextPanel() {
  const panel = activePanels()[panelIndex];
  if (!draft.frames[panel.id] && !draft.waived[panel.id]) return;
  await persistDraft();
  if (panelIndex < activePanels().length - 1) {
    panelIndex += 1;
    renderCapture();
  } else {
    renderReview();
  }
}

function coverageAsserted() {
  if (draft.mode !== "PHYSICAL_PACKAGE") return false;
  return ["FRONT", "BACK"].every(panel => draft.frames[panel]?.source === "camera" && !draft.waived[panel]);
}

function renderReview() {
  stopCamera();
  const panels = activePanels();
  $("#panelReview").innerHTML = panels.map(panel => {
    const frame = draft.frames[panel.id];
    if (!frame) return `<article class="review-panel waived"><div><strong>${esc(panel.title)}</strong><small>${draft.waived[panel.id] ? "Waived / skipped" : "Not captured"}</small></div></article>`;
    return `<article class="review-panel"><img src="${esc(frame.preview)}" alt="${esc(panel.title)} evidence"><div><span><strong>${esc(panel.title)}</strong><small>${esc(qualityLine(frame.quality))}</small></span><button class="text-button" data-retake="${panel.id}" type="button">Retake</button></div></article>`;
  }).join("");
  $$('[data-retake]').forEach(button => button.addEventListener("click", () => {
    panelIndex = panels.findIndex(panel => panel.id === button.dataset.retake);
    renderCapture();
  }));
  const asserted = coverageAsserted();
  $("#coverageStatus").className = `coverage-status ${asserted ? "" : "warn"}`;
  $("#coverageStatus").innerHTML = asserted ?
    "<strong>✓ Full required coverage confirmed</strong><span>The server may distinguish a proven absence from unreadable evidence.</span>" :
    "<strong>? Coverage is not asserted</strong><span>Missing declarations will remain indeterminate; the system will not accuse from incomplete evidence.</span>";
  $("#reviewMetadata").innerHTML = [
    ["Mode", titleCase(draft.mode)], ["Category", titleCase(draft.category)],
    ["Capture date", draft.captured_at], ["Evidence panels", Object.keys(draft.frames).length],
    ["Client UUID", draft.client_uuid.slice(0, 13) + "…"],
  ].map(([term, value]) => `<div><dt>${esc(term)}</dt><dd>${esc(value)}</dd></div>`).join("");
  $("#submitScanButton").textContent = navigator.onLine ? "Submit and evaluate" : "Queue until connected";
  showView("reviewView");
}

async function hashBlob(blob) {
  const digest = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, "0")).join("");
}

async function queueDraft(value = draft) {
  value.status = "QUEUED";
  await persistDraft(value);
  await dbPut("outbox", {client_uuid: value.client_uuid, attempts: 0, next_attempt_at: 0, queued_at: Date.now()});
  if ("serviceWorker" in navigator) {
    const registration = await navigator.serviceWorker.ready.catch(() => null);
    await registration?.sync?.register("lmpc-outbox").catch(() => {});
  }
  await refreshQueueCount();
}

function setSyncStep(index, title, message) {
  $("#syncTitle").textContent = title;
  $("#syncMessage").textContent = message;
  $$("#syncSteps span").forEach((span, at) => span.classList.toggle("active", at === index));
}

async function syncDraft(clientUuid, foreground = false) {
  const row = await dbGet("scans", clientUuid);
  if (!row) { await dbDelete("outbox", clientUuid); return; }
  const value = await hydrateDraft(row);
  value.status = "UPLOADING";
  await persistDraft(value);
  if (foreground) {
    showView("syncView");
    setSyncStep(0, "Verifying image hashes…", "The exact bytes accepted on this device are being identified before upload.");
  }
  const form = new FormData();
  form.append("client_uuid", value.client_uuid);
  form.append("captured_at", value.captured_at);
  form.append("mode", value.mode);
  form.append("category", value.category);
  form.append("buyer_type", value.buyer_type);
  form.append("package_shape", value.package_shape);
  form.append("coverage_asserted", String(coverageFor(value)));
  form.append("scale_reference", JSON.stringify({type: value.scale_type || "NONE"}));
  const dimensions = {};
  if (value.h_cm && value.w_cm) Object.assign(dimensions, {h_cm: value.h_cm, w_cm: value.w_cm});
  form.append("dimensions", JSON.stringify(dimensions));
  form.append("flags", JSON.stringify({is_imported: Boolean(value.is_imported), is_molded: Boolean(value.is_molded), other_law_requires_same_info: false}));
  form.append("ecommerce", JSON.stringify({url: value.listing_url || null, listing_text: value.listing_text || null}));
  const panelOrder = activePanelsFor(value).map(panel => panel.id).filter(panel => value.frames[panel]);
  for (const panel of panelOrder) {
    const frame = value.frames[panel];
    const digest = frame.sha256 || await hashBlob(frame.blob);
    frame.sha256 = digest;
    form.append("panels", panel);
    form.append("images", frame.blob, `${panel.toLowerCase()}.jpg`);
    form.append("image_sha256", digest);
  }
  if (foreground) setSyncStep(1, "Storing immutable originals…", "The local server verifies every hash before accepting the inspection.");
  const created = await request("/scans", {method: "POST", body: form});
  if (foreground) setSyncStep(2, "Applying the rulepack…", "OCR extracts evidence; deterministic rules decide each legal check.");
  const result = await request(`/scans/${created.scan_id}/reevaluate`, {method: "POST"});
  value.server_result = result;
  value.status = "SYNCED";
  await persistDraft(value);
  await dbDelete("outbox", value.client_uuid);
  await refreshQueueCount();
  releasePreviews(value);
  if (foreground) {
    draft = await hydrateDraft(await dbGet("scans", value.client_uuid));
    renderResult(result);
  } else {
    toast("A queued inspection synced successfully.");
  }
}

function activePanelsFor(value) {
  return value.mode === "ECOMMERCE_LISTING" ? [LISTING_PANEL] : PANELS;
}

function coverageFor(value) {
  if (value.mode !== "PHYSICAL_PACKAGE") return false;
  return ["FRONT", "BACK"].every(panel => value.frames[panel]?.source === "camera" && !value.waived?.[panel]);
}

async function drainOutbox() {
  if (!navigator.onLine) return;
  const entries = (await dbAll("outbox")).sort((a, b) => a.queued_at - b.queued_at);
  for (const entry of entries) {
    if (entry.next_attempt_at > Date.now()) continue;
    try {
      await syncDraft(entry.client_uuid, false);
    } catch (error) {
      entry.attempts += 1;
      entry.next_attempt_at = Date.now() + RETRY_DELAYS[Math.min(entry.attempts - 1, RETRY_DELAYS.length - 1)];
      await dbPut("outbox", entry);
      const row = await dbGet("scans", entry.client_uuid);
      if (row) { row.status = "FAILED"; row.failure_reason = error.message; await dbPut("scans", row); }
      break;
    }
  }
  await refreshQueueCount();
}

async function submitCurrent(forceQueue = false) {
  if (!Object.keys(draft.frames).length) { toast("Capture at least one evidence image."); return; }
  await queueDraft(draft);
  if (forceQueue || !navigator.onLine) {
    toast("Inspection saved in the offline queue.");
    showView("homeView");
    return;
  }
  try {
    await syncDraft(draft.client_uuid, true);
  } catch (error) {
    const row = await dbGet("scans", draft.client_uuid);
    if (row) { row.status = "FAILED"; row.failure_reason = error.message; await dbPut("scans", row); }
    toast(`Sync paused: ${error.message}`);
    renderReview();
  }
}

function resultCounts(evaluations) {
  const counts = Object.fromEntries(Object.keys(OUTCOMES).map(key => [key, 0]));
  evaluations.forEach(item => { counts[item.outcome] = (counts[item.outcome] || 0) + 1; });
  return counts;
}

function renderResult(result) {
  selectedOutcome = "ALL";
  selectedEvidence = result.images?.[0]?.panel || "";
  const counts = resultCounts(result.evaluations || []);
  $("#rulepackChip").textContent = result.rulepack ? `${result.rulepack.version} · sha256 ${result.rulepack.sha256}` : "Rulepack unavailable";
  const statusText = titleCase(result.overall || result.status);
  $("#resultSummary").innerHTML = `<section class="result-summary"><div><p class="eyebrow">EVALUATION COMPLETE</p><h1 id="resultTitle">${esc(statusText)}</h1><p>${result.evaluations?.length || 0} legal checks · captured ${esc(result.captured_at)} · coverage ${result.coverage_asserted ? "asserted" : "not asserted"}</p></div><div class="count-grid">${["FAIL", "REVIEW_REQUIRED", "INDETERMINATE", "PASS", "NOT_APPLICABLE", "SYSTEM_ERROR"].map(key => `<span>${esc(OUTCOMES[key][1])}<strong>${counts[key] || 0}</strong></span>`).join("")}</div></section>`;
  $("#evidenceTabs").innerHTML = (result.images || []).map(image => `<button type="button" data-panel="${esc(image.panel)}" class="${image.panel === selectedEvidence ? "active" : ""}">${esc(titleCase(image.panel))}</button>`).join("");
  $$('[data-panel]').forEach(button => button.addEventListener("click", () => selectEvidence(result, button.dataset.panel)));
  selectEvidence(result, selectedEvidence);
  $("#verdictFilters").innerHTML = ["ALL", ...Object.keys(OUTCOMES)].map(key => `<button type="button" data-filter="${key}" class="${key === selectedOutcome ? "active" : ""}">${key === "ALL" ? "All" : esc(OUTCOMES[key][1])}</button>`).join("");
  $$('[data-filter]').forEach(button => button.addEventListener("click", () => {
    selectedOutcome = button.dataset.filter;
    $$('[data-filter]').forEach(item => item.classList.toggle("active", item === button));
    renderVerdicts(result.evaluations || []);
  }));
  renderVerdicts(result.evaluations || []);
  renderDeclarations(result.declarations || []);
  $("#downloadGroup").hidden = !draft.report;
  $("#finalizeButton").hidden = Boolean(draft.report);
  if (draft.report) renderDownloads(draft.report.report_id);
  showView("resultView");
}

function selectEvidence(result, panel) {
  selectedEvidence = panel;
  $$('[data-panel]').forEach(button => button.classList.toggle("active", button.dataset.panel === panel));
  const image = (result.images || []).find(item => item.panel === panel);
  $("#evidenceImage").src = image?.url || "";
  $("#evidenceImage").alt = image ? `${titleCase(panel)} evidence` : "No evidence image";
}

function renderVerdicts(evaluations) {
  const order = Object.keys(OUTCOMES);
  const filtered = evaluations.filter(item => selectedOutcome === "ALL" || item.outcome === selectedOutcome)
    .sort((a, b) => order.indexOf(a.outcome) - order.indexOf(b.outcome));
  $("#verdictList").innerHTML = filtered.map(item => {
    const [icon, label] = OUTCOMES[item.outcome] || ["?", item.outcome];
    const citation = item.citation || {};
    const authority = [citation.gsr, citation.dated, citation.page ? `p. ${citation.page}` : ""].filter(Boolean).join(" · ");
    return `<details class="verdict-card" data-outcome="${esc(item.outcome)}"><summary><span class="verdict-icon" aria-hidden="true">${icon}</span><span><strong>${esc(item.clause || item.check)}</strong><small>${esc(item.reason)}</small></span><b class="verdict-outcome">${esc(label)}</b></summary><div class="verdict-detail"><dl><div><dt>Check</dt><dd>${esc(item.check)}</dd></div><div><dt>Authority</dt><dd>${esc(authority || "Citation attached in rulepack")}</dd></div><div><dt>Law version</dt><dd>${esc(item.law_version || "Current on capture date")}</dd></div><div><dt>Evidence</dt><dd><code>${esc(JSON.stringify(item.evidence || {}))}</code></dd></div></dl></div></details>`;
  }).join("") || '<div class="empty-state"><strong>No results in this group</strong><span>Choose another verdict filter.</span></div>';
}

function renderDeclarations(declarations) {
  $("#declarationList").innerHTML = declarations.map(item => {
    const weights = Object.entries(item.feature_weights || {});
    const max = Math.max(1, ...weights.map(([, value]) => Number(value)));
    return `<article class="declaration"><div class="declaration-head"><span>${esc(item.field)}</span><b>score ${Number(item.score || 0).toFixed(1)} · margin ${Number(item.margin || 0).toFixed(1)}</b></div><q>${esc(item.text)}</q><div class="score-bars">${weights.map(([name, value]) => `<div class="score-bar"><span>${esc(name)}</span><i><b style="width:${Math.max(0, Number(value) / max * 100)}%"></b></i><strong>${Number(value).toFixed(1)}</strong></div>`).join("")}</div></article>`;
  }).join("") || '<div class="empty-state"><strong>No declaration was identified confidently</strong><span>The rules will abstain where evidence is insufficient.</span></div>';
}

function renderDownloads(reportId) {
  $("#downloadGroup").hidden = false;
  $("#downloadGroup").innerHTML = `<a class="button secondary" href="${API}/reports/${encodeURIComponent(reportId)}/download?format=pdf">PDF</a><a class="button secondary" href="${API}/reports/${encodeURIComponent(reportId)}/download?format=docx">DOCX</a>`;
}

async function finalizeReport() {
  if (!draft.server_result?.scan_id) return;
  const button = $("#finalizeButton");
  button.disabled = true;
  button.textContent = "Rendering…";
  try {
    const report = await request(`/scans/${draft.server_result.scan_id}/report`, {method: "POST"});
    draft.report = report;
    await persistDraft();
    button.hidden = true;
    renderDownloads(report.report_id);
    toast(`Report version ${report.version} finalised.`);
  } catch (error) {
    button.disabled = false;
    button.textContent = "Finalise report";
    toast(error.message);
  }
}

async function renderHistory() {
  const rows = (await dbAll("scans")).sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  $("#historyList").innerHTML = rows.length ? rows.map(row => `<article class="history-item"><span class="history-icon">${esc(row.category.slice(0, 2))}</span><div><strong>${esc(titleCase(row.category))} · ${esc(row.captured_at)}</strong><small>${esc(titleCase(row.mode))} · ${esc(row.client_uuid.slice(0, 13))}…${row.failure_reason ? ` · ${esc(row.failure_reason)}` : ""}</small></div><span class="status-pill">${esc(row.status)}</span><button class="button secondary" data-open="${esc(row.client_uuid)}" type="button">${row.server_result ? "Open result" : row.status === "FAILED" || row.status === "QUEUED" ? "Retry sync" : "Resume"}</button></article>`).join("") : '<div class="empty-state"><strong>No inspections saved yet</strong><span>New captures will appear here, even while offline.</span></div>';
  $$('[data-open]').forEach(button => button.addEventListener("click", async () => {
    releasePreviews();
    draft = await hydrateDraft(await dbGet("scans", button.dataset.open));
    if (draft.server_result) renderResult(draft.server_result);
    else if (draft.status === "QUEUED" || draft.status === "FAILED") {
      if (!await dbGet("outbox", draft.client_uuid)) await queueDraft(draft);
      if (navigator.onLine) await syncDraft(draft.client_uuid, true).catch(error => toast(error.message));
      else renderReview();
    } else {
      panelIndex = Math.max(0, activePanels().findIndex(panel => !draft.frames[panel.id] && !draft.waived[panel.id]));
      renderCapture();
    }
  }));
  showView("historyView");
}

function bindEvents() {
  $("#homeButton").addEventListener("click", () => showView("homeView"));
  $("#resultHome").addEventListener("click", () => showView("homeView"));
  $("#newScanButton").addEventListener("click", beginScan);
  $("#historyButton").addEventListener("click", renderHistory);
  $$('[data-back="home"]').forEach(button => button.addEventListener("click", () => showView("homeView")));
  $("#modeInput").addEventListener("change", event => { $("#listingFields").hidden = event.target.value !== "ECOMMERCE_LISTING"; });
  $("#setupForm").addEventListener("submit", async event => {
    event.preventDefault();
    try { readSetup(event.currentTarget); await persistDraft(); renderCapture(); }
    catch (error) { toast(error.message); }
  });
  $("#captureBack").addEventListener("click", () => showView("setupView"));
  $("#reviewBack").addEventListener("click", () => { panelIndex = activePanels().length - 1; renderCapture(); });
  $("#discardButton").addEventListener("click", discardCurrent);
  $("#startCameraButton").addEventListener("click", startCamera);
  $("#shutterButton").addEventListener("click", captureCameraFrame);
  $("#fileInput").addEventListener("change", async event => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try { await processFile(file, "file"); } catch (error) { toast(error.message); }
  });
  $("#waiveInput").addEventListener("change", async event => {
    const panel = activePanels()[panelIndex].id;
    if (event.target.checked) {
      draft.waived[panel] = true;
      const frame = draft.frames[panel];
      if (frame?.preview) URL.revokeObjectURL(frame.preview);
      delete draft.frames[panel];
      await dbDelete("images", `${draft.client_uuid}:${panel}`);
      $("#acceptedPreview").hidden = true;
    } else delete draft.waived[panel];
    $("#nextPanelButton").disabled = !draft.frames[panel] && !draft.waived[panel];
    await persistDraft();
  });
  $("#retakeButton").addEventListener("click", async () => {
    const panel = activePanels()[panelIndex].id;
    if (draft.frames[panel]?.preview) URL.revokeObjectURL(draft.frames[panel].preview);
    delete draft.frames[panel];
    await dbDelete("images", `${draft.client_uuid}:${panel}`);
    $("#acceptedPreview").hidden = true;
    $("#nextPanelButton").disabled = true;
    resetQuality();
  });
  $("#nextPanelButton").addEventListener("click", nextPanel);
  $("#submitScanButton").addEventListener("click", () => submitCurrent(false));
  $("#saveOfflineButton").addEventListener("click", () => submitCurrent(true));
  $("#finalizeButton").addEventListener("click", finalizeReport);
  $("#languageButton").addEventListener("click", () => toast("Hindi interface catalogue is being prepared; legal findings remain exactly as issued by the rulepack."));
  window.addEventListener("online", () => { updateNetwork(); drainOutbox(); });
  window.addEventListener("offline", updateNetwork);
  navigator.serviceWorker?.addEventListener("message", event => {
    if (event.data?.type === "DRAIN_OUTBOX") drainOutbox();
  });
}

async function boot() {
  bindEvents();
  $("#dateInput").value = draft.captured_at;
  updateNetwork();
  await Promise.all([openDb(), checkStorage()]);
  await refreshQueueCount();
  if ("serviceWorker" in navigator) await navigator.serviceWorker.register("/sw.js").catch(() => {});
  setInterval(drainOutbox, 5 * 60 * 1000);
  if (navigator.onLine) drainOutbox();
}

boot().catch(error => toast(`Offline storage could not start: ${error.message}`));
