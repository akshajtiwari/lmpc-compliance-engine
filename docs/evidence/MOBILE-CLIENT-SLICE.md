# Mobile client slice — what is verified and what is not

**Date:** 2026-09-11
**Scope:** the Field app's offline/resilient sync slice, capture-quality gates,
deferred per-panel uploads, report download, and the server side those depend on.

This document exists so the next person does not have to re-derive what "done" means
here. It separates machine-verified claims from claims that still require physical
devices, and records what was deliberately not built.

## Verified in this repository (machine-checked)

Every item below is covered by an automated test that runs in the repository's CI
(`apps-ci.yml` and the mobile preview workflow):

- **Offline-first sync contract** (`apps/mobile/tests/sync.test.cjs`,
  `sync-policy.test.cjs`): SQLite outbox persistence across a killed process,
  SingleFlight drain, sequential upload with stop-on-connection-error, the
  5s/15s/60s/5m/30m/1h backoff ladder, account + server-fingerprint scoping, and
  duplicate suppression by `client_uuid`. The same suite verifies that only the
  `mobile-preview-release.yml` workflow enables the cleartext HTTP preview flag.
- **Capture-quality gates** (`apps/mobile/tests/quality.test.cjs`): Laplacian-variance
  blur detection, exposure bounds, glare-fraction hotspots, gallery-vs-camera source
  reporting, and the plain-language retake prompts, all computed on a downscaled JPEG
  probe in pure JS (`apps/mobile/src/quality.ts`).
- **Server quality persistence** (`tests/test_api_scans.py`): per-image
  `image_quality` is validated (unknown keys, ranges, warning shape) and stored in
  `scan_images.quality`; absent quality records as `null`. Advisory only — no rule
  reads it.
- **Deferred per-panel upload contract** (`tests/test_api_scans.py`):
  `POST /scans/deferred` declares panels and is idempotent by `client_uuid`;
  `POST /scans/{id}/images` accepts one panel per request, ignores exact re-sends,
  rejects undeclared panels, and answers 409 when a panel would receive different
  evidence; `POST /scans/{id}/complete-upload` refuses until every declared panel has
  arrived; `/process` refuses a scan that is missing panels; a full
  declare → per-panel → complete → process run reaches `EVALUATION_COMPLETE` with
  client-reported quality attached.
- **OpenAPI snapshot** (`docs/api/openapi.json`,
  `tests/test_openapi_snapshot.py`): the pinned snapshot matches the live schema;
  CI fails if a route drifts without regenerating.
- **Client flow**: `apps/mobile/src/api.ts` uses the deferred flow for every upload —
  begin (idempotent) → per-panel uploads, skipping panels the server already holds →
  complete-upload → process; a resumed attempt of an already-evaluated scan returns
  the existing result instead of reprocessing.
- **Scale-reference capture** (`apps/mobile/src/quad.ts`,
  `apps/mobile/tests/quad.test.cjs`, `apps/mobile/src/ScaleMark.tsx`): the officer lays
  an ISO ID-1 card on the package's display face, photographs it, and drags corner
  handles onto the card and (optionally) the display panel. The client validates only
  convexity and ID-1 aspect (±22%) as an advisory pre-gate; every physical conclusion
  is derived server-side.
- **Perspective-aware server measurement** (`lmpc/server/svc/scale.py`,
  `tests/test_scale_reference.py`): card-corner quads are converted to an image→
  millimetre homography (SVD-solved); the display panel's quad is back-mapped through
  the inverse homography and its px/mm is the area average `√(area_px/area_mm)`, which
  recovers exact panel dimensions in centimetres for coplanar rectangular faces. Mis-
  marked quads (non-convex, non-ID-1 aspect, tilted card, non-rectangular mapped panel,
  implausible scale) return `None`, so the engine abstains INDETERMINATE rather than
  guessing; with clean marks, `LMPC-R7-2-MIN-HEIGHT` evaluates to PASS on a synthetic
  camera (px/mm 12) where it previously could not run at all.
- **E-commerce listing capture** (`apps/mobile/src/ListingCapture.tsx`): a dedicated
  capture mode for third-party online listings — pasted shopper-visible text, optional
  source URL, and 1–6 screenshots labelled `LISTING`…`LISTING_6`, uploaded through the
  same deferred flow with `mode=ECOMMERCE_LISTING` and coverage asserted false (Rule
  6(10) checks the online display; screenshots never assert package coverage).
- **TypeScript**: `npm run typecheck` covers the full app, and `npm test` compiles the
  sync, quality and quad modules before running the unit tests.
- **Python suite**: the full server/engine test suite passes with the new routes,
  including the RBAC route-permission matrix and the repository line-budget guards
  (`scan_intake.py`, `scan_payload.py`, `scan_fields.py`, `report_store.py` were
  added to keep every module within budget).

## Requires a physical device (not verified here, not claimable)

The milestone gates in `docs/08-MOBILE-APP-PLAN.md` §10 remain open until they are run
on real hardware:

- M1: an installable APK launching without Metro, paired over real Wi-Fi, surviving a
  device restart.
- M2: a real end-to-end scan from phone camera to server verdict on device.
- M3/M4: device drills — airplane-mode capture, app kill and reopen, low-storage,
  camera-permission-denied, duplicate submit.
- M6: the ≤90 s capture budget on a named mid-range phone; a tagged workflow run
  producing an APK plus SHA-256 that actually installs.
- M7: iOS entirely (credentials absent).
- Cleartext/ATS behavior on-device (the plugin logic is unit-tested; the produced
  manifest is not verified by an emulator here).
- Scale-reference marking against a real photo of a real card on a real package
  (the homography math is tested on synthetic cameras; the drag UX has not been held
  by a hand).

## Published preview

Tag `v0.3.0-preview` carries the Windows portable build and the Field APK together on one
GitHub release, both with SHA-256 checksums; install steps live in the top-level README.
The APK is built by CI from a clean checkout that passes typecheck, lint, unit tests and
expo-doctor — but M1–M4 and M6 above still require a physical phone. That APK predates
the scale-reference and listing capture slices; they will ride the next tagged build.

## Deliberately not built

- OCR/extraction improvement: the engine is validated (0 false accusations across
  2,700 evaluations) but extraction recall (~50%) is a separate server workstream
  with its own ≥90% target.