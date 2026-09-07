# Flow — What the User Does, What the System Does

One scan, end to end. Left column is the officer's experience; right column is the
machinery. Detail lives in `01-ARCHITECTURE.md` and `04-ENGINEERING-PLAN.md`.

---

## The 60-second version

```
Officer opens PWA → photographs 4 faces → taps Submit
        ↓
  upload + hash (WORM)
        ↓
  OCR (PaddleOCR, en+hi) → text + polygons
        ↓
  extractors → ExtractedLabel (candidate facts, with confidence)
        ↓
  RULE ENGINE (plain Python, versioned rulepack)
    gates → presence → format → semantics → typography → placement
        ↓
  6-state verdicts + evidence crops + citations
        ↓
Officer reviews, corrects, approves → PDF / DOCX (hashed) → repository
```

The law is **not** read at scan time. It was compiled into a rulepack in Week 1 by hand,
with review. The engine executes that rulepack and nothing else.

---

## Step by step

| # | What the user sees | What is happening underneath |
|---|---|---|
| 1 | Logs in on a phone browser | Keycloak OIDC → JWT carrying role + jurisdiction; every later query is row-filtered by it server-side |
| 2 | "Photograph the front panel" — an outline guides framing | Capture client checks blur, glare and perspective **before** accepting the frame. Bad frames are rejected on-device, not diagnosed later |
| 3 | Repeats for back, sides, base | A *surface coverage model* tracks which faces exist. This is what later separates "MRP is missing" from "we never saw the back" |
| 4 | Optionally lays a bank card in frame | An ISO ID-1 card (85.60 mm) or AprilTag is the scale reference. Without it, millimetre checks abstain rather than guess |
| 5 | Taps Submit; sees "Processing" | Originals go to WORM storage, sha256 recorded. A job is queued (Redis + Dramatiq). The API returns immediately — nothing blocks on OCR |
| 6 | Steps appear one by one, live | PaddleOCR (English + Devanagari) returns text tokens **with polygons**. Geometry is preserved because typography rules need it |
| 7 | — | Extractors pull candidate facts — MRP, net quantity, dates, address, consumer care — and normalise units, money and dates into `ExtractedLabel`. Fuzzy lexicon match + a scored layout rubric pick between competing candidates (§ below); a weak winning margin yields `INDETERMINATE` rather than a guess. Every field keeps its source token IDs |
| 8 | **"Not applicable — Rule 26"** *(sometimes the flow ends here)* | Applicability gates run **first**: bulk/industrial (Rule 3), small pack ≤10 g/ml, fast food, DPCO (Rule 26). An exempt package is never evaluated, so it can never be falsely accused |
| 9 | A list of rule cards, colour-coded | The rule engine walks the rulepack: presence → format → semantics → typography → placement. Each check is plain Python a person can read |
| 10 | Cards say PASS, FAIL, or **INDETERMINATE** | Six states, not two. `INDETERMINATE` means the evidence or the law is insufficient — blurry glyphs, unphotographed panel, a measurement sitting on a threshold |
| 11 | Taps a card: sees the cropped evidence, the number measured, the threshold, the gazette citation | Every verdict stores the crop, the computed value with its confidence interval, the rule and sub-rule, the gazette file/page, and the rulepack hash |
| 12 | Corrects a mis-read MRP, re-runs | The correction is an **append-only revision**. Both runs are kept and diffable. Nothing is overwritten |
| 13 | Approves → downloads PDF or DOCX | One verdict object renders to both (not a PDF→DOCX conversion). The report carries a content hash and the rulepack version |
| 14 | Finds it later by brand or manufacturer | Postgres + `pg_trgm`; the product is deduplicated on (manufacturer, brand, barcode) so its inspection history accumulates |

---

## Where the pieces live

| Layer | Runs where | Holds legal logic? |
|---|---|---|
| PWA capture client | Officer's browser | **No** — camera, quality gates, upload, rendering |
| API + rule engine | Server (FastAPI, modular monolith) | **Yes** — the rulepack, and only the rulepack |
| OCR / measurement workers | Server, async queue | No — they produce evidence, not verdicts |
| Postgres + MinIO | Server | Scans, verdicts, WORM originals, reports |
| Gazette PDFs & extracts | Repo, **build-time only** | Compiled by hand into the rulepack in Week 1 |

---

## The two ideas that shape everything

**1. Absence of evidence is not evidence of absence.** If the back panel was never
photographed, "MRP not found" is `INDETERMINATE`, not `FAIL`. The coverage model in
step 3 exists solely to make that distinction possible.

**2. There is no language model in the system.** The problem statement asks for
*rule-based* compliance checking, and that is literally what runs. Field identification is
fuzzy lexicon matching plus a scored layout rubric; report wording is templated strings
from the rulepack; "which documents affect Rule 6" is a SQL query over the amendment
ledger. Vision AI (PaddleOCR) produces *evidence*; deterministic Python draws every
*conclusion*. Nothing in the verdict path can hallucinate, drift between runs, or fail to
explain itself.
