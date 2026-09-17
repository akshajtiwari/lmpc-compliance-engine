# The physical device drill

**Scope:** the real-device gates that no amount of laptop testing substitutes for. Every
automated suite in this repository is green; that is exactly why this document exists.
Until the drills below are run and their tables filled in, `v0.5.0-preview` and every
later tag remain unvalidated hardware, and the M1–M6 device gates in
[`08-MOBILE-APP-PLAN.md`](../08-MOBILE-APP-PLAN.md) §10 stay open.

Record each drill on the day it is run, with the build tag, the phone model and the
Android version. A drill that was not written down did not happen.

## Before you start

| | |
|---|---|
| Windows ZIP | the tag's `LMPC-Compliance-<tag>-windows-x64.zip`, checksum-verified with `sha256sum -c SHA256SUMS.txt` |
| APK | the tag's `LMPC-Field-<tag>-android.apk`, checksum verified |
| Network | one private Wi-Fi or hotspot; both devices on it; no VPN active on the laptop |
| Phone | the chosen mid-range Android test phone (name it here: ______), ≥2 GB free storage |
| Time | about 2 hours for all drills if nothing fails; budget a full afternoon the first time |

The laptop-side smoke test that needs no phone at all: extract the ZIP, run
`LMPC-Compliance.exe --self-test`, then `LMPC-Compliance.exe --addresses`. The address a
phone could dial must be listed as usable — a VPN tunnel address ranked first is the bug
that Phase 9 exists to prevent, and this is the 30-second check for it.

## M1 — Install and pair

1. Copy the APK to the phone, allow "install unknown apps" for the file manager, install.
2. Launch **LMPC Field**. It must reach the pairing screen **without Metro, without Expo
   Go, without any development server**.
3. Run the EXE, click **Allow phone connections**, scan the QR.
4. Verify the pairing page flips to "Phone connected", and `--addresses` output matches
   the address the app reports in Settings.
5. **Restart both.** Kill the app, reopen it — the session must restore without re-pairing.
   Restart the EXE — the pairing still holds.

| Date | Build | Phone | Result | Notes |
|---|---|---|---|---|
| | | | | |

## M2 — One real end-to-end scan

1. On the phone, create an investigation (name, location, type `RETAIL_SWEEP`).
2. Scan a real retail package with all four panels from the camera.
3. The verdict returns on the phone; the scan appears inside the folder; the folder's
   stats update.
4. Scan a second package with the MRP obscured — the report must name the exact clause
   that fails, not a generic failure.
5. On the Workbench, open the same folder: both scans are there with the same verdicts.

| Date | Build | Phone | Products | Verdicts matched Workbench | Notes |
|---|---|---|---|---|---|
| | | | | | |

## M3 — Capture quality and coverage

1. Photograph a label in dim light and accept a retake prompt when offered one.
2. Photograph a glare-washed panel — the app must demand a retake, not upload it.
3. Import a panel from the gallery: the inspection must **not** be allowed to assert
   coverage, and the report must say so.
4. Mark a scale reference (ID-1 card) and verify the measured letter height lands where
   a ruler says it should, ±10 %.

| Date | Build | Phone | Retakes offered | Coverage gate held | Scale measurement | Notes |
|---|---|---|---|---|---|---|

## M4 — Offline-first sync

1. Airplane mode **before** creating anything: create an investigation and scan one
   product. Everything queues on the device.
2. Turn the network back on: exactly one investigation and one scan appear server-side,
   in the right order, with the same client UUIDs (no duplicates).
3. Airplane mode mid-upload: kill the app during a panel upload, reopen — the upload
   resumes without duplicating the scan server-side.
4. Create an offline scan whose parent investigation has never synced, then go online:
   the parent must sync first, and the child must not burn retries against the wall.
5. Kill the app, reopen, open a past report **with Wi-Fi off** — it must render from the
   device cache.

| Date | Build | Phone | Order held | No duplicates | Cache-first report | Notes |
|---|---|---|---|---|---|---|

## M5 — Reports on the phone

1. Open a completed scan, download the PDF **field copy** — every page carries the
   "not legally finalized" watermark, and the inspection remains editable afterwards.
2. Download the DOCX; it opens and carries the same findings and integrity footer.
3. On the Workbench, finalise the same scan as a reviewer; re-download from the phone —
   the unwatermarked, reviewer-signed copy arrives.
4. Export the investigation's consolidated report and confirm it covers every product.

| Date | Build | Phone | Watermark on every page | Both formats | Finalised copy differs | Notes |
|---|---|---|---|---|---|---|

## M6 — Release quality on the named test phone

1. Time a full capture-to-verdict on the mid-range phone: the budget is **90 seconds**.
2. Deny camera permission first, then grant it — recovery must be clean.
3. Fill storage until the low-storage guard engages; the app must refuse a capture it
   cannot persist, not crash.
4. Submit the same inspection twice (double-tap the submit button quickly) — the server
   must hold exactly one scan (the idempotency UUID at work).

| Date | Build | Phone | Capture time | All four drills | Notes |
|---|---|---|---|---|---|

## The upgrade-path drill (SQLite v2 → v3 on the device)

The device schema gained `investigations`, `investigation_id` on inspections and the
`scan_results` cache. The migration has been reasoned about; it has never run against a
database that holds real rows.

1. Install the **previous** tag's APK (`v0.4.0`), pair, and capture two products.
2. Note the products' client UUIDs and the device's captured evidence list.
3. Install the new APK **over** it (do not uninstall).
4. Verify: both inspections still listed, evidence photographs still open, one is
   uploadable and lands in "Unfiled inspections", the outbox drains once, and no
   evidence file is orphaned or deleted before the server acknowledged it.

| Date | From → to | Phones rows before | Rows after | Outbox drained | Notes |
|---|---|---|---|---|---|

## The TLS pairing drill (blocked until the phone pins certificates)

The server side is ready and tested: `LMPC-Compliance.exe --tls` (or
`make dev-lan-tls` from source) serves HTTPS with a self-signed certificate whose
SHA-256 pin travels in the QR, and the pin is re-minted when the network moves. What
does not exist yet is the phone half: an unmodified React Native fetch rejects a
self-signed chain before any application code runs, so **every preview APK so far
cannot connect to an HTTPS pairing**. That needs a certificate-pinning transport
(e.g. a pinning fetch module) wired into `apps/mobile/src/api.ts` and verified on a
device — until then this drill cannot pass, and TLS stays opt-in.

When a pinning build exists:

1. Run the server with `--tls`; confirm the pairing page shows the HTTPS address and
   the console prints the pin.
2. A **modified** phone build enrolls over HTTPS; the QR's pin matches the certificate
   the phone received.
3. Present a different self-signed certificate (a second server on the same port):
   the phone must refuse it — the pin is the whole point.
4. Record the drill here with the build tags.

## What this document is not

It is not a substitute for the automated suites — those already ran, and their results
are recorded in the other evidence documents. This page exists so that the hardware step,
when someone has the phone and the laptop in the same room, takes an hour instead of a
day, and so that its result is recorded where the next person can find it.