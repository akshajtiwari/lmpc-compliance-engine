# Native Mobile Application Plan

**Decision date:** 2026-09-10  
**Status:** Implementation-ready plan; native-mobile direction requested; implementation not started  
**Supersedes:** the PWA-as-primary-client decision in Parts 4.1 and 17 of the older
architecture documents. The existing PWA remains a fallback and a source of tested
capture behavior while the native client is built.

## 1. Product decision

Build two clients around the existing shared FastAPI backend:

1. **LMPC Field**, an installable React Native application for Android and iOS. It is the
   primary field-capture experience.
2. **LMPC Workbench**, a separate desktop-oriented website for review, correction,
   dashboards, administration, search, and report finalization. It follows after the
   mobile critical path is complete.

React Native shares the application logic and most UI across Android and iOS. Camera,
local-network permissions, build signing, and device testing remain platform-specific and
must be tested separately; “one codebase” does not mean “one untested binary.”

The phone is not the compliance server. It captures trustworthy evidence, works offline,
uploads when the server is reachable, and displays the server's decision. OCR, legal
rules, shared history, report generation, and dashboards remain on the server.

## 2. What “local server” means

During development and the SIH demonstration:

- A laptop or departmental PC runs FastAPI, PostgreSQL, and filesystem object storage.
- No S3 service is required.
- The phone and server join the same private Wi-Fi or hotspot.
- The mobile app connects to the server's LAN address, for example
  `http://192.168.1.20:8000/api/v1`, not `127.0.0.1`.
- The installed preview app runs without Metro or a USB connection.
- Offline capture continues without the server, but OCR and compliance evaluation wait
  until the server can be reached.

The current server and Windows portable preview listen only on `127.0.0.1`. That is safe
for desktop use but unreachable from a phone. LAN access will be a deliberate opt-in mode;
loopback remains the default.

The current Windows portable preview also keeps scan metadata only for its running
session. Mobile development should use the PostgreSQL local stack so repository and
history behavior are real. A later packaging milestone can make the LAN server one-click,
but it must not pretend that an in-memory store satisfies the repository requirement.

## 3. Target architecture

```text
Android / iOS: LMPC Field
  camera + quality gates + offline drafts + outbox + own results
                         |
                  private LAN / HTTPS
                         |
FastAPI modular monolith + OCR + deterministic rule engine
                         |
           PostgreSQL + local filesystem objects
                         |
Desktop browser: LMPC Workbench (later)
  review + corrections + overrides + dashboards + administration
```

The rulepack and all legal thresholds remain server-side. A rule change must never require
a mobile release.

## 4. Technology choice

### Mobile

- React Native with Expo and TypeScript strict mode.
- Expo development builds from the beginning, not an Expo Go-only workflow. This leaves
  room for the native image-quality module and platform network configuration.
- Expo Router for native Android/iOS navigation.
- `expo-camera` for the first camera vertical slice, including flash/torch and barcode
  support where available.
- A small local Expo native module backed by OpenCV for blur, glare, exposure, and
  perspective measurements. The first release evaluates a captured frame before accepting
  it; live preview analysis is added only if device profiling shows it remains responsive.
- Expo SQLite for durable draft/outbox metadata.
- Expo FileSystem for pending image files.
- Expo SecureStore for the rotating refresh token; the short-lived access token remains
  in memory.
- Generated TypeScript API types from FastAPI's OpenAPI document. API types are never
  maintained by hand.

### Web workbench, later

- A separate TypeScript web application under `apps/web`.
- It consumes the same generated API client but has its own routes and desktop layouts.
- The existing static PWA stays available until the new workbench reaches feature parity.

### Repository layout

```text
apps/
  mobile/                 Expo React Native application
  web/                    later enforcement workbench
packages/
  api-client/             generated OpenAPI types + typed request wrapper
  design-tokens/          shared names/colors only; no shared page components required
lmpc/                     existing Python engine and FastAPI server
```

## 5. Responsibility boundary

| Capability | Mobile | Server | Web workbench |
|---|---:|---:|---:|
| Login and role enforcement | UI/token custody | **Authority** | UI/token custody |
| Guided package capture | **Primary** | Validate upload | Non-guided upload only |
| Blur/glare/exposure/perspective | **Pre-upload gate** | Recheck/record | — |
| Offline drafts and retry queue | **Primary** | Idempotent receiver | — |
| OCR and declaration extraction | — | **Primary** | Review display |
| Legal applicability and verdicts | — | **Only authority** | Review display |
| Rule-info explanations | Display | **Source** | Display |
| Own recent scans/results | Display | **Source** | Display |
| Cross-officer repository/search | Limited | **Source** | **Primary** |
| Corrections, overrides, finalization | Not in mobile v1 | **Authority** | **Primary** |
| Dashboards and administration | — | **Source** | **Primary** |
| PDF/DOCX generation | Download/share | **Primary** | Download/manage |

## 6. Mobile user journeys

### 6.1 First run and server connection

1. Explain that LMPC Field requires a departmental/local server for analysis.
2. Scan a pairing QR shown by the server, or enter the server address manually.
3. Call `/readyz` and `/version`; show server identity, rulepack version, and connection
   status before saving it.
4. Log in. Store the refresh token in SecureStore and keep the access token only in memory.
5. Require an explicit new login if the saved server identity changes unexpectedly.

The pairing QR conveys an address and server fingerprint, not a privileged login token.

### 6.2 Physical package inspection

1. Start scan and choose category, inspection date, buyer type, and package shape.
2. Explain buyer type before capture. `Retail consumer` is the normal packaged-retail
   path. Industrial/institutional selection warns that the applicability gate may stop
   before OCR.
3. Capture front and back, then prompted side panels when declarations continue there.
4. Each frame is measured locally. Reject blur, heavy glare, bad exposure, or severe
   perspective with a plain-language correction.
5. Allow retake. Gallery import is supporting evidence only and cannot establish complete
   physical coverage.
6. Optionally capture an ISO ID-1 scale reference or enter dimensions for typography
   checks.
7. Review all panels. The app sets `coverage_asserted=true` only when all required panels
   were captured through the controlled camera path and none was waived.
8. Submit immediately or queue locally.

### 6.3 E-commerce inspection

1. Select e-commerce mode.
2. Record listing URL and paste listing text.
3. Attach listing screenshots.
4. Submit through the same outbox and show only the rules applicable to listing evidence.

### 6.4 Results

1. Show upload and processing as separate stages.
2. Show the overall state and all six verdict states without relying on color alone.
3. Every rule card includes `Rule info`: requirement, current reason, decision method,
   evidence required, authority, and limitation.
4. If processing stopped at an applicability gate, state clearly that OCR did not run and
   the image was not rejected.
5. Allow the officer to see their recent inspections and download/share finalized reports.
   Corrections, overrides, and legal finalization remain in the web workbench.

## 7. Offline data and sync contract

### Local records

```text
scan_drafts(client_uuid, metadata_json, state, created_at, updated_at)
frames(id, client_uuid, panel, file_uri, sha256, source, quality_json)
outbox(client_uuid, operation, attempts, next_attempt_at, last_error)
server_links(client_uuid, scan_id, server_version, synced_at)
```

Images live under the application's document directory, grouped by `client_uuid`. They
are deleted only after the server acknowledges the matching SHA-256 and the configured
post-sync retention window expires.

### State machine

```text
DRAFT -> READY -> QUEUED -> UPLOADING -> PROCESSING -> COMPLETE
                       |        |             |
                       +------ FAILED <-------+
                                  |
                                RETRY
```

Rules:

- `client_uuid` is created once and reused for every retry.
- Repeated submission must return the existing scan, never create a duplicate.
- Drain the outbox on app foreground, manual `Sync now`, and confirmed network regain.
  Background execution is an optimization, not a correctness dependency.
- Keep exponential backoff: 5 s, 15 s, 60 s, 5 min, 30 min, then hourly.
- App termination or phone restart must not lose a captured panel or change its hash.
- The first vertical slice can use the existing multipart scan endpoint. Resumable image
  chunks become mandatory before pilot use on unreliable field networks.

## 8. Required server work before mobile can be called functional

1. Add an opt-in LAN launch mode (`make dev-lan` and equivalent `--lan` server flag) that
   binds to `0.0.0.0`; keep loopback as default.
2. Print the chosen LAN URL and a pairing QR. Refuse LAN mode when authentication is
   disabled.
3. Add trusted-server identity/fingerprint data to the version/bootstrap response.
4. Make the API URL configurable in the mobile preview build.
5. Keep refresh-token-in-body support for the native client and verify rotation/reuse
   revocation through contract tests.
6. Return explicit processing status and stable error codes suitable for polling.
7. Generate and check in a pinned OpenAPI snapshot for the TypeScript client.
8. Record capture source and quality measurements per image.
9. Add resumable/chunked uploads after the initial end-to-end slice.
10. For production/on-prem deployment, use HTTPS. Cleartext private-LAN HTTP is permitted
    only in the explicitly labeled development/preview profile.

Native clients are not subject to browser CORS, but the later separate web origin will
need a narrow allow-list or a same-origin reverse proxy.

## 9. Platform-specific network rules

- Android preview builds need a debug/preview-only network security configuration for the
  local HTTP server. Production builds deny cleartext traffic.
- iOS needs a Local Network usage description. Local-address transport exceptions belong
  only in the preview configuration; production uses trusted HTTPS.
- Both platforms need clear camera permission text and a useful recovery screen when the
  user denies access.
- LAN access should be limited to a private network/firewall profile. The server must never
  expose an authentication-disabled instance on `0.0.0.0`.

## 10. Implementation milestones and gates

### M0 — LAN and API foundation

- Add safe LAN server mode, bootstrap/version identity, pairing information, and mobile
  auth contract tests.
- Generate the TypeScript API client.

**Gate:** a physical phone on the same Wi-Fi reaches `/readyz`, logs in, refreshes its
token, and cannot access a scan outside its role/jurisdiction.

### M1 — Installable application shell

- Create `apps/mobile`, navigation, design tokens, server setup, authentication, secure
  session restoration, connection banner, and error handling.
- Configure development and preview build profiles.

**Gate:** an installable Android preview APK launches without Metro, pairs to the local
server, logs in, and survives an app restart.

### M2 — One real end-to-end scan

- Implement setup, front/back camera capture, resize, SHA-256, review, multipart upload,
  processing polling, overall result, and rule-info sheets.
- Use the submitted nutrition-label photograph as a regression scenario with buyer type
  `RETAIL`.

**Gate:** the phone captures and submits a real retail package; OCR runs; a nutrition-only
close-up returns incomplete evidence instead of out of scope; choosing industrial gives an
explained applicability stop before OCR.

### M3 — Trustworthy capture and coverage

- Add native blur/glare/exposure/perspective measurements, side-panel prompts, retake,
  scale reference, storage checks, and coverage rules.

**Gate:** poor frames are rejected before upload, and no incomplete/gallery-based capture
can send `coverage_asserted=true`.

### M4 — Offline-first sync

- Implement SQLite/FileSystem drafts, persistent outbox, network-aware retries, manual
  sync, duplicate handling, and safe post-sync cleanup.

**Gate:** capture in airplane mode, kill and reopen the app, reconnect, sync exactly once,
and confirm that server image hashes match the phone hashes.

### M5 — Field results and reports

- Add own-scan history, processing recovery, evidence panel viewer, six-state filtering,
  explanations, and finalized PDF/DOCX download/share.

**Gate:** every result is understandable without consulting server logs, and every verdict
can open its rule explanation and evidence.

### M6 — Android release quality

- Add typecheck, lint, unit/component tests, API-contract checks, Android build, and device
  smoke tests to CI.
- Publish an internally installable APK from a tagged GitHub workflow run.

**Gate:** capture completes in at most 90 seconds on a chosen mid-range Android test phone;
offline, permission-denied, low-storage, process-killed, and duplicate-submit drills pass.

### M7 — iOS parity

- Apply iOS camera/local-network/privacy configuration and validate the same workflows on
  a physical iPhone.
- Produce a signed internal/TestFlight build when Apple credentials are available.

**Gate:** the M1–M6 functional suite passes on iOS, with platform exceptions documented.

### M8 — Separate web workbench

- Build the desktop review/repository/dashboard application after the mobile path is
  stable.
- Migrate existing review, correction, override, search, dashboard, and report functions
  screen by screen; retire only the duplicated PWA screens that reach parity.

**Gate:** role matrix, jurisdiction scoping, correction/re-evaluation history, report
finalization, search, and dashboards pass end-to-end tests.

## 11. CI plan

Every pull request:

- Python server/engine suite and OpenAPI compatibility check.
- Mobile formatting, lint, TypeScript check, and unit/component tests.
- Android preview compilation to catch native/config-plugin failures.
- Secret/package audit and a check that production profiles do not permit cleartext HTTP.

Tagged mobile preview:

- Build an installable Android APK.
- Start the backend fixture, run the end-to-end scan contract, and publish APK plus SHA-256
  as GitHub release assets.
- iOS build runs separately on macOS after signing credentials exist.

## 12. Requirement traceability

| Problem-statement requirement | Planned owner and proof |
|---|---|
| Scan/analyze package images | Mobile guided capture -> server OCR test |
| Mandatory declarations | Existing server extraction/rules; improve against labelled set |
| Correctness/completeness/placement | Existing deterministic stages; evidence shown in clients |
| Missing declarations | Server only after mobile coverage assertion |
| Readability/font size | Mobile scale-reference flow + server measurement confidence |
| Compliance and violation reports | Existing server PDF/DOCX; mobile download, web finalization |
| Photographs/supporting evidence | Mobile hashes + server immutable local objects |
| Product repository/history | PostgreSQL + later web search; own history in mobile |
| Role-based secure access | Existing server RBAC + native secure token custody |
| Dashboards | Later web workbench, backed by existing dashboard endpoints |
| Search/retrieval | Later web workbench, backed by existing scan-search endpoint |
| Architecture/deployment docs | This plan plus existing build and architecture documents |

## 13. Known risks and non-negotiable tests

| Risk | Response |
|---|---|
| Phone cannot reach laptop localhost | Explicit LAN mode, pairing test on physical device |
| LAN HTTP exposes credentials/evidence | Preview-only exception; auth mandatory; HTTPS before pilot |
| Native camera differs by device | Fixed target-device matrix and physical tests |
| Background sync is suspended by OS | Foreground/network/manual drains are authoritative |
| Gallery image falsely proves coverage | Capture-source tracking; gallery never asserts coverage |
| App rewrite distracts from weak OCR | Keep OCR workstream and ≥90% declaration target separate |
| Android works but iOS is assumed | Independent iOS gate and signing plan |
| Mobile becomes an admin console | Keep mobile v1 focused on capture, own results, and sync |

The mobile app does not solve the measured extraction gap by itself. The current engine is
strong at avoiding false accusations but identifies mandatory declarations on only about
half of correctly legible real packages in the recorded campaign. OCR/extraction quality
remains a parallel server workstream and must reach the existing ≥90% target.

## 14. Planning references

- React Native/Expo camera: https://docs.expo.dev/versions/latest/sdk/camera/
- Persistent mobile SQLite: https://docs.expo.dev/versions/latest/sdk/sqlite/
- Encrypted token storage: https://docs.expo.dev/versions/latest/sdk/securestore/
- Mobile file upload/storage: https://docs.expo.dev/versions/latest/sdk/filesystem/
- Network-state listener: https://docs.expo.dev/versions/latest/sdk/network/
- Expo development and internal builds: https://docs.expo.dev/build/introduction/
- Android network security configuration:
  https://developer.android.com/privacy-and-security/security-config
- Apple Local Network privacy:
  https://developer.apple.com/documentation/bundleresources/information-property-list/nslocalnetworkusagedescription
- Apple local-network transport setting:
  https://developer.apple.com/documentation/bundleresources/information-property-list/nsapptransportsecurity/nsallowslocalnetworking
