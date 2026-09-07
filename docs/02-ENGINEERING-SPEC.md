# Legal Metrology Compliance System — Engineering Specification

**Audience:** implementers.
**Prerequisites:** `00-TEAM-BRIEF.md`, `01-ARCHITECTURE.md`.
**Source material:** verified against the live DoCA site and primary gazette PDFs on
2026-09-04. Council analysis archived at `.claude/council-cache/council-agents-1788466125.md`.

---

## Part I — Verified source facts

### I.1 Reproducing the verification

```bash
# The page: TLS chain is EXPIRED. -k is required.
curl -sSLk -A "Mozilla/5.0" https://consumeraffairs.gov.in/pages/legal-metrology-act -o lm.html

# Extract every rules/amendment link
grep -oiE '<a[^>]*href="[^"]*\.pdf"[^>]*>[^<]{0,120}' lm.html | grep -i packaged

# CRITICAL: hrefs are http:// but port 80 does NOT answer. Rewrite to https.
#   curl http://consumeraffairs.gov.in/...  -> "Failed to connect ... port 80 after 135243 ms"
#   curl https://consumeraffairs.gov.in/... -> HTTP 200

# Classify each document before deciding how to read it
pdfinfo   doc.pdf          # Producer field is a strong signal
pdffonts  doc.pdf          # no fonts => scanned
pdftotext -layout doc.pdf - | tr -cd 'A-Za-z' | wc -c   # <500 chars => scanned
pdfimages -list doc.pdf    # full-page image coverage => scanned
```

### I.2 Corpus classification (measured)

| Document | URL fragment | Pages | Producer | Verdict |
|---|---|---|---|---|
| Base PCR 2011 | `8_1732871406.pdf` | 83 | OmniPage CSDK 15.5 | SCANNED (0 chars) |
| Amd 2011 (1st) | `8(i)_0_1732860957.pdf` | 1 | none | SCANNED |
| Amd 2011 (3rd) | `8(iii)_0_1732861046.pdf` | 2 | DPE Build 5656 | TEXT (2 495) |
| Amd 2012 | `8(v)_0_1732861119.pdf` | 9 | none | SCANNED |
| Amd 2013 | `8(vii)_…` | ? | none | SCANNED |
| Amd 2015 | `8(x)_0_1732870750.pdf` | 6 | none | SCANNED |
| Amd 2017 | `8(xii)_0_1732871346.pdf` | 14 | GPL Ghostscript 9.06 | TEXT (15 076) |
| Amd 2021 | `230946_1732871433.pdf` | 4 | iTextSharp 5.5.13.1 | TEXT (3 034) |
| Amd 2022 Mar | `GSR226_1732871458.pdf` | 3 | iTextSharp 5.5.13.1 | TEXT (2 367) |
| Amd 2022 QR | `Notification…(QR Code)_…pdf` | 3 | iTextSharp 5.5.13.1 | TEXT (2 367+) |

Heuristic: **pre-2017 → scanned, 2017+ → digital.** Verify, do not trust the heuristic.

### I.3 Language handling

The Hindi text layer is **mojibake** — the gazettes embed a legacy non-Unicode
Devanagari font. `pdftotext` yields `प्राजधकार से प्रकाजित` where the page reads
`प्राधिकार से प्रकाशित`. English extracts perfectly.

**Rule: parse the English. Discard the Hindi.** Detect the boundary rather than
hardcoding it:

```python
def english_ratio(page_text: str) -> float:
    latin = sum(c.isascii() and c.isalpha() for c in page_text)
    deva  = sum('ऀ' <= c <= 'ॿ' for c in page_text)
    return latin / max(latin + deva, 1)

# english_ratio > 0.85 => treat as the English rendition
```

For the 83-page scan: Hindi pp. 1–~41, English pp. ~42–83. Clean, high-contrast
serif — OCRs well with `tesseract -l eng --psm 6` or PaddleOCR.

### I.4 Preferred baselines (avoid OCRing 83 pages)

| Source | Pages | Form | Cut-off |
|---|---|---|---|
| `legalmetrologymh.in/public/temp/368/02d3c4fef3045bc21d90ba000a28357e.pdf` | 31 | Word→PDF, **English only**, 67 114 chars | "as amended up to GSR dt. 31.10.2021 w.e.f. 01.04.2022" |
| `thc.nic.in/Central%20Governmental%20Rules/Legal%20Metrology%20(Packaged%20Commodities)%20Rules,2011.pdf` | 54 | iLovePDF, text layer | consolidated |
| DoCA `Book_on_Legal_Metrology_Packaged_Commodities_Rules,2011_with_all_amendments_whatsnews.pdf` | — | official compilation | ~Jan 2025 |

**Use a compilation as the baseline, then diff every instrument after its cut-off.**
A compilation is never authoritative for current law — the Maharashtra one is a
*state officer's* compilation and carries no legal force. Cite the gazette, always.

### I.5 The amendment chain is machine-readable

Every notification ends with:

> *Note: The principal rules were published … vide G.S.R. number 202(E), dated the
> 7th March, 2011 and was last amended vide notification number G.S.R. 226(E), dated
> the 28th March, 2022.*

```python
NOTE_RE = re.compile(
    r"principal rules were published.*?G\.S\.R\.\s*(?:number\s*)?(?P<base>\d+\s*\(E\)).*?"
    r"dated\s+the\s+(?P<base_date>\d{1,2}\w*\s+\w+,?\s+\d{4}).*?"
    r"last amended.*?G\.S\.R\.\s*(?:number\s*)?(?P<prev>\d+\s*\(E\)).*?"
    r"dated\s+the\s+(?P<prev_date>\d{1,2}\w*\s+\w+,?\s+\d{4})",
    re.S | re.I,
)
```

Walk `prev` pointers backwards from the newest instrument. **A break in the chain means
you are missing a document** — an automated completeness proof, and a strong demo point.

### I.6 Amendment grammar

Instruments are written in a rigid register that parses into patch operations:

```
In the said rules, in rule 7,-
  (i)   for sub-rule (2), the following sub-rule shall be substituted, namely:- "…"
  (ii)  for sub-rule (3), the following sub-rule shall be substituted, namely:- "…"
  (iii) For the Table-I, the following table shall be substituted, namely:- "…"
  (iv)  Table II shall be omitted;
```

Operation verbs to support: `shall be substituted` → `substitute` · `shall be inserted`
→ `insert` · `shall be omitted` → `omit` · `shall be renumbered` → `renumber` ·
`shall be read as` → `correct` · `shall come into force` → `commence`.

**Parse to propose. A human accepts.**

### I.7 Glyph loss — a real trap we hit

The 2017 gazette's own text layer renders `A ≤ 50` as `A < 50`; the `≤` is lost. Boundary
conditions (`<` vs `≤`) change verdicts at exactly the values most likely to be
litigated. **Every numeric boundary must be human-verified against the rendered page
image**, and the rulepack must store the page region so a reviewer can re-check it.

### I.8 Server behaviour

| Observation | Value |
|---|---|
| 2.4 MB PDF over HTTPS | 17.3 s |
| 1.0 MB PDF over HTTPS | 5.1 s |
| Port 80 | never connects (135 s timeout) |
| Sequential fetches | 5 of 8 failed on one pass; 3 retries with 8 s backoff recovered 4 |
| TLS | chain expired |

Ingestion needs: `https` rewrite, `verify=False` **scoped to the fetcher only**,
retries with backoff, per-host concurrency of 1, and a quarantine bucket. Never in the
request path of a scan.

---

## Part II — Current law for the checks we implement

> Verified against the primary 2017 gazette (`8(xii)_0_1732871346.pdf`, pp. 11–12) and
> cross-checked against the Maharashtra compilation. **Re-verify before the finale** —
> instruments exist through 2026.

### II.1 Rule 7 — Principal display panel

**7(1)** Packages of capacity **≤ 10 cm³** may use a card or tape as the PDP.
*(Was 5 cm³ in the 2011 base text — changed by the 2017 amendment.)*

**7(2)** Height of any numeral **and letter** shall be as per Table-I.
*(Base 2011 text said "any numeral" only, and keyed the table to net quantity.)*

**Table-I — current, substituted by the 2017 amendment:**

| # | PDP area A (cm²) | Min height (mm) | Blown/formed/molded (mm) |
|---|---|---|---|
| 1 | A ≤ 50 | 1.0 | 1.5 |
| 2 | 50 < A ≤ 100 | 1.5 | 3.0 |
| 3 | 100 < A ≤ 500 | 2.5 | 4.0 |
| 4 | 500 < A ≤ 2500 | 4.0 | 6.0 |
| 5 | 2500 < A | 6.0 | 6.0 |

**Table-II was omitted** by the same amendment. The base 2011 PDF still shows it. Anyone
building from that PDF implements repealed law.

**7(3)** Width of a letter or numeral ≥ **⅓ of its height**, except numeral `1` and
letters `(i)`, `(I)`, `(l)`.

**7(4)** PDP area, excluding top, bottom, flanges of cans, and shoulders/necks of
bottles and jars:

| Shape | Area |
|---|---|
| Rectangular (one side is clearly the PDP) | height × width of that side |
| Cylindrical / near-cylindrical | **0.40** × height × circumference |
| Any other shape | **0.40** × total surface area |

**7(5)** Sub-rules (1)–(4) do not apply where the same information is required by
another law — **except** for net weight, retail sale price, expiry/best-before/use-by
date, and consumer care details, which always remain in scope.

### II.2 Rule 8 — Declaration placement

Every declaration shall appear on the principal display panel. The area surrounding the
**quantity declaration** shall be free from printed information:

- above and below: ≥ **1×** the height of the numeral in the declaration
- left and right: ≥ **2×** the height of the numeral

### II.3 Rule 9 — Manner of declaration

- 9(1)(a) legible and prominent
- 9(1)(b) numerals of retail sale price and net quantity in a colour **contrasting
  conspicuously** with the label background
  - proviso (a): blown/formed/moulded glass or plastic need not contrast
  - proviso (b): handwritten declarations must be clear, unambiguous, legible
- 9(2) must not require reading **through** a liquid commodity
- 9(3) an outer container/wrapper must also bear all declarations, unless transparent
  and the inner declarations are easily readable through it
- 9(4) particulars in **Hindi (Devanagari)** or **English**; other languages permitted
  in addition

### II.4 Rule 6 — Mandatory declarations (base text; verify current wording)

Name and address of manufacturer/packer/importer · common or generic name · net
quantity in standard units · month and year of manufacture/pre-packing/import · retail
sale price as `MRP Rs. …` inclusive of all taxes · consumer care name, address,
telephone, e-mail.

Explanations I–III (from the base text, p. 43): a name without "manufactured by"/"packed
by" is presumed to be the manufacturer; a brand owner appearing as marketer is liable;
food articles fall under the food law instead.

Rule 6(3): stickers may **not** be affixed to alter a required declaration — **except** a
lower-MRP sticker, which must not cover the original MRP.

### II.5 Checks that need no calibration — implement first

| Check | Rule | Method |
|---|---|---|
| Letter width ≥ ⅓ height | 7(3) | Glyph bounding-box ratio in rectified pixels |
| Quantity clear space ≥ 1×/2× numeral height | 8 | Pixel distance to nearest printed token ÷ numeral pixel height |
| MRP/net-quantity contrast | 9(1)(b) | Foreground/background luminance from the glyph mask |
| Language is Hindi or English | 9(4) | Script detection on declaration tokens |
| Sticker covering MRP | 6(3) | Edge/texture discontinuity over the MRP polygon |

All are **dimensionless ratios or classifications** — no mm, no marker, no uncertainty
interval. Real violations, detectable on any photograph. Build these before AprilTag.

---

## Part III — Data contracts

### III.1 `ExtractedLabel` (Pydantic → JSON Schema)

```json
{
  "schema_version": "label-extraction/1.0",
  "scan_id": "scan_01J...",
  "created_at": "2026-09-04T12:04:15Z",

  "package": {
    "form": "rectangular_carton",
    "sale_channel": "physical_retail",
    "commodity_category": "ordinary_retail_package",
    "is_imported": true,
    "classification_confidence": 0.91,
    "classification_source": "officer_confirmed",
    "dimensions_mm": { "height": 182.0, "width": 118.0, "depth": 45.0,
                       "source": "officer_measured" },
    "pdp_area_cm2": { "value": 214.8, "method": "rule_7_4_a",
                      "interval_95": [209.1, 220.6] }
  },

  "coverage": {
    "expected_surfaces": ["front","back","left","right","top","bottom"],
    "captured_surfaces": ["front","back","left","right","top","bottom"],
    "complete": true,
    "officer_confirmed": true
  },

  "images": [{
    "id": "img_back",
    "original_sha256": "…",
    "width_px": 4032, "height_px": 3024,
    "surface": "back",
    "quality": { "acceptable": true, "blur_score": 147.2,
                 "glare_fraction": 0.012, "clipped_text": false },
    "calibration": { "method": "apriltag_coplanar", "marker_size_mm": 40.0,
                     "local_mm_per_px": 0.041, "relative_error_95pct": 0.038 }
  }],

  "tokens": [{
    "id": "tok_101", "image_id": "img_back",
    "text": "MRP ₹120.00 incl. of all taxes", "script": "latin",
    "polygon_norm": [[0.12,0.53],[0.62,0.52],[0.62,0.58],[0.12,0.59]],
    "ocr_confidence": 0.97, "ocr_model": "paddleocr:<weights-sha>"
  }],

  "declarations": {
    "mrp": {
      "status": "found",
      "candidates": [{
        "raw": "MRP ₹120.00 incl. of all taxes",
        "currency": "INR", "amount_minor": 12000,
        "tax_inclusive_phrase_present": true,
        "confidence": 0.96,
        "evidence": { "image_id": "img_back", "token_ids": ["tok_101"],
                      "polygon_norm": [[0.12,0.53],[0.62,0.52],[0.62,0.58],[0.12,0.59]] }
      }]
    },
    "net_quantity": {
      "status": "found",
      "candidates": [{ "raw": "Net Qty: 500 g", "value": "500", "unit": "g",
                       "dimension": "mass", "confidence": 0.98,
                       "evidence": { "image_id": "img_front",
                                     "token_ids": ["tok_024","tok_025"] } }]
    },
    "manufacture_date": {
      "status": "ambiguous",
      "candidates": [{ "raw": "PKD 08/26", "normalized": "2026-08",
                       "precision": "month", "kind": "packing", "confidence": 0.78,
                       "evidence": { "image_id": "img_bottom", "token_ids": ["tok_301"] } }]
    },
    "responsible_parties": [{
      "role": "importer",
      "name_raw": "Example Imports Pvt Ltd", "address_raw": "…",
      "address_components": { "postal_code": "110020", "country": "IN" },
      "confidence": 0.88,
      "evidence": { "image_id": "img_back",
                    "token_ids": ["tok_141","tok_142","tok_143"] }
    }]
  }
}
```

Non-negotiable properties:

- **Multiple candidates**, never a prematurely chosen value
- **Raw and normalized** side by side
- **Per-field evidence** (image + token polygons)
- **Per-field confidence**
- Explicit `found` / `not_found` / `ambiguous`
- Coverage manifest and officer confirmations
- Versioned model provenance

`status` values must distinguish `not_found` (searched, absent) from `ambiguous`
(several plausible candidates) — they lead to different verdicts.

### III.2 Rule definition (YAML)

```yaml
id: LMPC.R7.LETTER_HEIGHT
revision: 3
title: Minimum height of declarations
authority: binding
severity: major

applies_when:
  evaluator: package_rule7_applicability
  parameters:
    excluded_categories: ${legal_tables.rule7_exclusions}
    always_in_scope_fields: [net_weight, retail_sale_price, expiry_date, consumer_care]

requires:
  - package.pdp_area_cm2
  - declarations[*].typography.height_mm_interval
  - declarations[*].evidence

check:
  evaluator: minimum_character_height
  parameters:
    threshold_table: rule7_table_1
    uncertainty_policy: interval_guard_band

citations:
  - instrument_id: GSR-629E-2017
    provision: rule.7.subrule.2.table_1
    page: 11
    source_sha256: "…"
    source_region: [0.06, 0.29, 0.94, 0.88]

effective:
  from: 2018-01-01
  to: null

tests:
  - fixture: flat_carton_height_above_threshold.json
    expected: PASS
  - fixture: flat_carton_interval_straddles_threshold.json
    expected: INDETERMINATE
  - fixture: back_surface_not_captured.json
    expected: INDETERMINATE
```

Threshold tables live in reviewed data files, never inline in code:

```yaml
rule7_table_1:
  source: GSR-629E-2017
  reviewed_by: [reviewer_a, reviewer_b]
  boundary_note: "≤ verified against page image; text layer renders it as <"
  rows:
    - { max_area_cm2: 50,   normal_mm: 1.0, molded_mm: 1.5, inclusive: true }
    - { max_area_cm2: 100,  normal_mm: 1.5, molded_mm: 3.0, inclusive: true }
    - { max_area_cm2: 500,  normal_mm: 2.5, molded_mm: 4.0, inclusive: true }
    - { max_area_cm2: 2500, normal_mm: 4.0, molded_mm: 6.0, inclusive: true }
    - { max_area_cm2: null, normal_mm: 6.0, molded_mm: 6.0, inclusive: true }
```

**No Python `eval`. No general-purpose DSL in v1.** Named evaluators registered in a
dict, each a plain, unit-tested function.

### III.3 Amendment operation ledger

```yaml
instrument:
  id: GSR-418E-2026
  title: Legal Metrology (Packaged Commodities) Third Amendment Rules, 2026
  publication_date: 2026-05-29
  gazette_id: CG-DL-E-01062026-273053
  source_sha256: "…"
  source_url: "https://egazette.gov.in/WriteReadData/2026/273053.pdf"
  status: notified          # draft | notified | corrigendum | withdrawn
  authority: binding        # binding | advisory | guideline | faq
  amends: GSR-202E-2011
  previous_amendment: GSR-128E-2026
  commencement:
    kind: publication_date  # or explicit_date | transition_period
  reviewed_by: [reviewer_a, reviewer_b]

operations:
  - op: insert
    target: rule.4.explanation.2
    source_page: 3
    source_region: [0.08, 0.31, 0.92, 0.59]
    normalized_text_sha256: "…"
  - op: substitute
    target: rule.27.subrule.1
    source_page: 3
```

Operations: `insert` · `substitute` · `omit` · `renumber` · `correct` · `commence` ·
`expire` · `relax` · `clarify_nonbinding`.

### III.4 Rule result

```json
{
  "rule_result_id": "rr_01J...",
  "rule_id": "LMPC.R6.MRP.PRESENCE",
  "rule_revision": 4,
  "rulepack_id": "lmpc-2026.05.29-r1",
  "status": "FAIL",
  "machine_status": "FAIL",
  "officer_disposition": "pending",

  "applicability": {
    "applicable": true,
    "facts_used": { "sale_channel": "physical_retail",
                    "package_class": "ordinary_retail_package" }
  },

  "reason_code": "DECLARATION_NOT_FOUND_WITH_COMPLETE_COVERAGE",
  "explanation": "No qualifying MRP declaration was found on six confirmed package surfaces.",

  "evidence": {
    "coverage_manifest_id": "coverage_123",
    "image_ids": ["img_front","img_back","img_left","img_right","img_top","img_bottom"],
    "candidate_ids_rejected": ["cand_44"],
    "rejection_reasons": ["promotional price without MRP context"]
  },

  "citation": {
    "instrument_id": "GSR-202E-2011",
    "provision": "rule.6.subrule.1.clause.e",
    "page": 12,
    "source_sha256": "…",
    "source_region": [0.11, 0.24, 0.91, 0.47]
  },

  "execution": {
    "engine_version": "verifier:1.4.2",
    "extractor_version": "extractor:0.9.7",
    "code_git_sha": "…",
    "input_manifest_sha256": "…"
  }
}
```

`explanation` is rendered from a **template with real facts** — the template string lives
in `rules.yaml`, one per verdict state, in English and Hindi. Wording is therefore stable
across runs and translatable, which a generated summary would not be.

### III.5 Execution manifest (reproducibility)

```json
{
  "input_asset_hashes": ["sha256:…"],
  "coverage_manifest_hash": "sha256:…",
  "rulepack_id": "lmpc-2026.05.29-r1",
  "rulepack_sha256": "…",
  "ocr_engine": "paddleocr",
  "ocr_weights_sha256": "…",
  "extractor_container_digest": "sha256:…",
  "verifier_container_digest": "sha256:…",
  "code_git_sha": "…",
  "parameters_sha256": "…",
  "hardware": "NVIDIA-T4/CUDA-12.1",
  "started_at": "…", "completed_at": "…"
}
```

Rulepacks and model weights are **immutable artifacts**. Reprocessing creates a new
`evaluation_run`; it never overwrites the old one.

---

## Part IV — Relational schema

| Entity | Key fields |
|---|---|
| `agency` | tenant, jurisdiction |
| `user` | IdP subject, agency |
| `role_assignment` | officer · supervisor · rule_admin · auditor |
| `inspection` | officer, location, started/completed, status |
| `product` | brand/common identity |
| `package_variant` | GTIN, quantity, form, dimensions, category |
| `scan` | inspection, variant, status, device, timestamps |
| `scan_surface` | expected vs captured surface, coverage confirmation |
| `asset` | URI, media type, size, SHA-256, original/derived |
| `image_derivation` | parent asset, operation, parameters, transform matrix |
| `calibration_run` | method, marker id/size, intrinsics, error interval |
| `ocr_run` | model, version, weights hash, parameters, runtime |
| `ocr_token` | text, polygon, script, confidence |
| `extraction_run` | extractor version, schema version |
| `field_candidate` | field, raw + normalized, confidence, evidence |
| `field_resolution` | selected candidate, machine/officer source, revision |
| `legal_instrument` | G.S.R., source, dates, hashes, authority status |
| `amendment_operation` | target, op, effective dates, source region |
| `rulepack` | version, hash, validity interval, approval signatures |
| `rule_definition` | rule id, evaluator, parameters, citation |
| `evaluation_run` | full execution manifest |
| `rule_result` | status, reason, evidence, citation |
| `officer_review` | prior value, new value, reason, signer |
| `report` | format, report hash, template version |
| `audit_event` | actor, action, object, before/after hashes, timestamp |

Normalized tables for identity and lifecycle; **JSONB** for immutable extraction and
evaluation payloads. Rule validity uses `tstzrange` with a GiST exclusion constraint so
two rulepacks cannot claim the same instant.

### IV.1 Evidence integrity

At capture: hash the original on-device · preserve EXIF · record server receipt time,
device id, app version, GPS + accuracy where authorized · upload **original bytes**,
never editor-transformed · server recomputes the hash and rejects mismatches · store a
signed capture manifest.

At storage: versioned MinIO buckets · Object Lock / WORM in production · every
derivative carries its own hash and parent link · transformations and parameters stored ·
officer reviews are **append-only**.

Audit hash chain:

```
event_hash = SHA256(previous_event_hash || canonical_json(event))
```

This makes undetected alteration substantially harder. It does **not** by itself confer
legal admissibility — production needs trusted timestamps, key management, access
logging, retention policy and digital signatures. Say this out loud rather than
overclaiming.

---

## Part V — Pipelines

### V.1 Extraction

```
A. Capture validation
   blur (variance of Laplacian) · glare fraction · exposure clipping ·
   perspective angle · surface coverage checklist · marker presence

B. Geometric processing
   lens distortion correction · plane homography from marker or page corners ·
   rectification to metric coordinates · PDP segmentation

C. OCR routing
   PaddleOCR (en + devanagari) · per-region script detection ·
   full-resolution crops for small text rather than whole-image downscale

D. Candidate generation
   regex + layout heuristics per field · proximity to keywords
   ("MRP", "Net Qty", "PKD", "Mfd", "Customer Care") ·
   optional VLM ONLY to associate a value with a field, never to invent one

E. Normalization
   units (g/kg/ml/l/cm/m/N) · dates (many gazette-permitted forms) ·
   currency (₹, Rs., INR; minor units as integers)
   — always alongside the untouched raw string
```

### V.2 Verification stages

| Stage | Inputs | Verdicts |
|---|---|---|
| 0 Applicability | commodity category, consumer type, sale channel, import status, quantity, special regime | `PASS` / `NOT_APPLICABLE` |
| 1 Evidence sufficiency | coverage manifest, per-image quality | `PASS` / `INDETERMINATE` |
| 2 Presence | resolved field statuses | `PASS` / `FAIL` / `INDETERMINATE` |
| 3 Syntax | normalized values | `PASS` / `FAIL` |
| 4 Semantics | cross-field consistency, plausibility | `PASS` / `FAIL` / `REVIEW_REQUIRED` |
| 5 Typography | height intervals, width ratio, contrast | `PASS` / `FAIL` / `INDETERMINATE` |
| 6 Placement | PDP membership, clear-space ratios | `PASS` / `FAIL` / `INDETERMINATE` |

### V.3 Uncertainty policy

```python
def threshold_verdict(interval_95: tuple[float, float], threshold: float) -> str:
    lo, hi = interval_95
    if lo >= threshold:  return "PASS"
    if hi <  threshold:  return "FAIL"
    return "INDETERMINATE"          # the interval straddles the threshold
```

```
Absence → FAIL only if:
    rule is applicable
AND required surface coverage is complete
AND image quality is acceptable
AND no qualifying candidate exists
AND absence-confidence threshold is met
otherwise → INDETERMINATE or REVIEW_REQUIRED
```

Even then, an automated absence finding stays **provisional** until an officer confirms it.

### V.4 No language model — and what replaces one

The deployed system contains **no LLM**. The problem statement specifies *rule-based*
compliance checking; every job a language model would conventionally absorb is handled by
a small deterministic component instead. Full design in `04-ENGINEERING-PLAN.md` §4.1.

| Job | Shipped mechanism |
|---|---|
| Associate a field with the right text block | Fuzzy lexicon match + scored layout rubric; wins only on an absolute floor **and** a margin over the runner-up, else `INDETERMINATE` |
| Read an OCR-mangled heading (`MR.P`, `एम.आर.पी`) | Normalised edit distance against a curated synonym lexicon (`rapidfuzz`), accept at ≥0.85 |
| Explain a result in plain language | Templated strings in `rules.yaml`, typed slots, en + hi |
| Locate source text for a researcher | SQL over the amendment operation ledger + Postgres FTS |
| Propose amendment operations | Gazette grammar parser (§I.6) |

Nothing in the verdict path can hallucinate, drift between runs, or fail to explain
itself. Vision AI (PaddleOCR) produces **evidence**; deterministic Python draws every
**conclusion**. Legal effectiveness, supersession, numeric comparison, unit conversion,
date arithmetic, presence determination, character dimensions, evidence sufficiency,
final status and citations are all code — none of them were ever a model's job, and now
no model exists to be blamed for them.

---

## Part VI — Physical measurement

### VI.1 Marker card

40–60 mm AprilTag (36h11) or ArUco marker · printed millimetre scale · unique card id ·
version + checksum · **matte finish** to suppress glare.

### VI.2 Procedure

1. Place the marker immediately beside the declaration, **on the same physical plane**
2. Camera near perpendicular; **no digital zoom**
3. Capture three frames
4. Detect marker corners
5. Correct lens distortion
6. Compute plane homography
7. Rectify the declaration crop into metric coordinates
8. Segment glyph pixels (binarize; do not trust OCR boxes)
9. Measure representative glyph heights locally
10. Aggregate across frames → interval

### VI.3 Bounding box ≠ legal letter height

An OCR box includes line spacing, matras, ascenders, descenders, background noise,
perspective error, and sometimes several lines. Required: rectify → segment glyph pixels
→ measure **selected representative glyphs** → record *which* glyphs were measured →
exclude box padding → report the minimum supported height or another legally reviewed
statistic.

For Devanagari the **shirorekha** (headstroke) and vowel marks make Latin-style cap
height meaningless. The measurement convention must be written down and legally
reviewed — do not let it be an accident of the code.

### VI.4 Curved surfaces

A single homography is invalid on a bottle. Options: move the marker and capture small
locally-planar regions · use a flexible calibrated scale strip · fit a cylinder from
several views and unwrap · photogrammetry/depth then map text onto the surface ·
**return `INDETERMINATE` beyond the validated curvature range**.

Hackathon scope: flat cartons and near-flat pouch regions. **Demo the graceful
abstention on a bottle** — it is a feature.

### VI.5 Accuracy

Engineering targets to benchmark (do not promise in advance):

- Flat matte panel, coplanar marker, good light: **<5% relative error at p95**
- Known-dimension or non-coplanar reference: **<10%**
- Anything worse: screening only

Validate against printed test charts measured with a calibrated loupe or calliper.
Render as:

```
Estimated height: 2.18 mm
95% interval:     2.06 – 2.30 mm
Method:           40 mm coplanar AprilTag
Calibration:      accepted (rel. err. 3.8%)
```

**Never show `2.18 mm` without the interval and the method.**

---

## Part VII — Latency budget

| Phase | Target |
|---|---|
| Live quality checks | < 200 ms/frame |
| Barcode / marker detection | < 300 ms |
| Upload (usable 4G/Wi-Fi) | 2–8 s |
| Server preprocessing | 0.2–0.8 s/image |
| OCR on modest GPU | 0.5–2 s/image |
| OCR on CPU | 2–8 s/image |
| Structured extraction | < 300 ms |
| Optional VLM fallback | 1–6 s |
| Rule engine | **< 100 ms** |
| Report generation | 1–4 s, asynchronous |

First provisional verdict: **6–15 s** after upload on a GPU-backed deployment. Guided
capture itself takes 20–45 s.

Expose progress as `uploaded → image quality → OCR → extraction → verification → report`.
**Never hold one HTTP request open for the whole job** — the staged pass/fail UX is a
natural fit for polling or SSE over a job id.

---

## Part VIII — Evaluation

### VIII.1 Three datasets

**Gold package set** — real packages, multiple categories and shapes, hand-annotated per
field, with a ground-truth compliance judgement per implemented rule. Target 150–300
packages; annotate every field, not just violations.

**Physical typography calibration set** — printed charts at known letter heights
(0.8/1.0/1.5/2.5/4.0/6.0 mm), on matte and glossy stock, flat and curved, verified with
callipers. This is what turns a measurement claim into a defensible one.

**Synthetic perturbation set** — programmatic blur, glare, rotation, JPEG artefacts,
occlusion, sticker overlay, applied to gold images with known ground truth. Measures
graceful degradation and validates that abstention increases rather than errors.

### VIII.2 Metrics

| Level | Metric |
|---|---|
| OCR | CER / WER per script, per surface |
| Field | precision / recall / F1 per field; normalization accuracy |
| Measurement | error distribution vs calliper truth; interval coverage (a 95% interval should contain truth ~95% of the time) |
| Rule | 3-way confusion (`PASS`/`FAIL`/`INDETERMINATE`) per rule |
| System | **FAIL precision** (primary) · abstention rate · officer-override rate |

**FAIL precision is the headline number.** A false violation against a real manufacturer
is far costlier than a missed one. Report the rule of three honestly: zero false
positives in *n* samples bounds the true rate only at roughly **3/n** — 0/50 means
"≤6%", not "0%".

### VIII.3 Adversarial cases judges will appreciate

Promotional price mistaken for MRP · multiple addresses with different roles ·
manufacture vs expiry date confusion · "500 g + 50 g free" · sticker covering the
original declaration · imported package with a local importer sticker · tiny embossed
text · reflective curved bottle · Hindi heading with an English value · e-commerce
screenshot with no physical package · QR code carrying details not visibly printed ·
package with one surface missing.

---

## Part IX — Build sequence

**Week 1 — legal and data foundations.** Source registry + immutable document store ·
PDF classification · text extraction · amendment ledger · choose supported legal scope ·
8–12 rules reviewed · extraction and verdict schemas · **rule fixtures written before
any UI** · begin collecting gold packages.

**Week 2 — capture and OCR.** Guided capture · surface coverage model · blur/glare/
perspective checks · direct uploads with hashing · PaddleOCR worker · evidence-polygon
viewer · barcode/QR.

**Week 3 — extraction and deterministic verifier.** Candidate extractors · unit/date/
money normalization · applicability questionnaire · presence, syntax and semantic
checks · six-state results · execution manifest.

**Week 4 — typography, reports, review.** Ratio checks first, then marker card and
homography · calibration dataset · intervals and guard bands · officer correction flow ·
PDF/DOCX · audit events and report hashes.

**Week 5 — hardening.** Evaluation harness · adversarial set · performance profiling ·
offline/local deployment · **rule-source outage drill** · backup/restore test · demo
rehearsal with an unseen product.

At the finale: **freeze model and rulepack versions.** Spend the event on integration,
evidence presentation and reliability — not on changing models.

---

## Part X — How recommendations change with the facts

| Premise | Status after verification | Design consequence |
|---|---|---|
| PDFs are scanned | **Half true** — base is, post-2017 amendments are not | Classify per file; OCR only ~50% |
| Hindi-half / English-half | **True for the base only** | Detect language per page; never hardcode |
| No official consolidation exists | **False** | Use a compilation as baseline, diff after its cut-off |
| Font thresholds keyed to net quantity | **False — repealed in 2017** | Key to PDP area; compute area via rule 7(4) |
| Latest PDF wins | **False** | Draft vs notified; publication vs commencement date |
| Amendment list ends at 2022 | **False — runs through 2026** | Ledger must be open-ended; re-verify before the finale |
| Package dimensions are authoritative | Unresolved | Secondary calibration / cross-check only |
| Cloud OCR is acceptable to the department | Unresolved | Keep evidence processing on controlled infrastructure until told otherwise |

**The legal-source architecture does not change with any of these.** What changes is how
much OCR and manual consolidation the team has to do.

---

## Part XI — Open items requiring a human decision

1. **Measurement convention for Devanagari letter height** — shirorekha included or not?
   Blocks Rule 7 verdicts on Hindi declarations. Needs legal review.
2. **`<` vs `≤` at every Table-I boundary** — verify against page images, not text layers.
3. **Current instruments through 2026** — the ledger must be walked to the newest
   notification before the finale; the 2026 amendments were not in the original brief.
4. **Reviewer substitute** — a student team has no legal-metrology officer. Document a
   two-student review with gazette page + hash citations, and state plainly in the demo
   that production requires qualified sign-off. Honesty scores better than a fake
   approval workflow.
5. **Rule 7(5) interaction with food law** — food articles fall partly under FSSAI.
   Do not conflate the two regimes; the applicability stage must separate them.
