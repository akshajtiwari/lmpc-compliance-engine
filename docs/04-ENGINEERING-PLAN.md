# Engineering Plan — Legal Metrology Compliance System

**Status:** execution plan. Binds the verified law in `02-ENGINEERING-SPEC.md` to a dated,
owned, gated build.
**Legal baseline frozen:** 2026-09-07, against `source-extracts/` (primary gazette).
**Reads with:** `00-TEAM-BRIEF.md` (why) · `01-ARCHITECTURE.md` (design decisions) ·
`02-ENGINEERING-SPEC.md` (contracts, verified law) · `03-BUILD-GUIDE.md` (code).

This document does not restate architecture. It answers: *what gets built, by whom, in
what order, and what has to be true before we move on.*

---

## 1. Document disposition — resolve before Week 1

`../legal-metrology-compliance-system-technical-spec.md` is a parallel draft whose §4
(Regulatory Rule Specification) contradicts the notified law. It must not be a build
input.

| Action | Detail |
|---|---|
| **Demote** | Move to `docs/archive/2026-09-technical-spec-superseded.md` with a header pointing at `02-ENGINEERING-SPEC.md` Part II as the sole rule authority |
| **Harvest** | Port §6 DDL, §7 API surface, §11.2 offline idempotency, §9 rule-versioning into `02` (§§ IV / new Part XII) — these are sound and not yet covered |
| **Discard** | §4 entirely. Table values, PDP formula, Rule 26 reading and exemption list are wrong (see §3.2) |
| **Rule** | One rule authority in this repo. Any document stating a threshold must cite gazette file + page |

**Owner:** tech lead. **Gate:** no `rules.yaml` commit lands before this is done.

---

## 1.5 Build-time vs runtime — what actually ships to a phone

None of these documents, and none of the gazette text, is an app asset. The law is
compiled **once, offline, by hand, with review** into a small rulepack. The phone and the
server only ever execute the rulepack.

| Artifact | Lives where | Ships to device? |
|---|---|---|
| `source-extracts/*.txt`, `*.pdf`, `*.png` (gazette text, ~97k chars + scans) | Repo + immutable source store, build-time only | **No** |
| `00`–`04` planning docs, superseded technical spec | Repo, human-readable only | **No** |
| `rules.yaml` + `tables.yaml` + `checks.py` (the compiled rulepack, a few KB) | Baked into the server image at build; version + sha256 pinned | Server yes, phone no |
| Rulepack **version string + hash** | Returned with every verdict | **Yes** — displayed, not interpreted |
| Gazette **citation strings** (file, page, clause) | Fields inside `rules.yaml` | **Yes** — as text on the report |
| PWA capture client | Browser | Camera, quality gates, upload, result rendering only |

Consequences the build must honour:

1. The app **never fetches, parses, or "reads" a government PDF at scan time.** Ingestion
   of new notifications is an asynchronous, human-approved pipeline that produces a *new
   rulepack version* — it is never in the request path of a scan.
2. The phone client holds **no legal logic.** It captures, checks image quality, uploads,
   and renders what the server decided. No thresholds, no comparisons, no rule text.
3. A verdict cites the law by **string**, not by document. The citation is data typed into
   `rules.yaml` during Week 1 review, so a report can name G.S.R. 629(E) p.11 without any
   PDF existing on the device or the server at runtime.
4. This is why §1 matters: the superseded spec was never going to run anywhere — the harm
   is that a wrong Table-I gets **hand-copied into `tables.yaml`** during Week 1 and then
   executes on every scan for the rest of the project.

---

## 2. Scope commitment — problem statement → what we ship

Every PS requirement gets one of: **BUILD** (v1), **PARTIAL** (bounded subset, limits
stated in the UI), **ABSTAIN** (system says it cannot decide — a deliverable, not a gap).

| # | PS requirement | v1 | How |
|---|---|---|---|
| 1 | Image upload / product scanning | BUILD | Guided multi-surface PWA capture + web upload; blur/glare/perspective rejection at capture |
| 2 | Extraction of declarations | BUILD | PaddleOCR (en + Devanagari) → candidate extractors → `ExtractedLabel` |
| 3 | Detection of mandatory declarations | BUILD | Presence checks R01–R07 (§5) |
| 4 | Correctness & completeness | BUILD | Format R08–R12 + consistency R19 |
| 5 | Placement of declarations | PARTIAL | Rule 8 clear-space + on-PDP test on flat/near-flat faces; curved → `INDETERMINATE` |
| 6 | Font size & readability | PARTIAL | Ratio checks (Rule 7(3), 9(1)(b)) uncalibrated; absolute mm (Rule 7(2)) only with fiducial on a flat panel; else `INDETERMINATE` |
| 7 | Missing / misleading / non-standard | PARTIAL | Missing + non-standard = deterministic. **"Misleading" is out of scope** — it requires facts off the label; stated explicitly in report footer |
| 8 | Compliance reports PDF + editable | BUILD | WeasyPrint + docxtpl from one verdict object (not a PDF conversion) |
| 9 | Photographs & supporting evidence | BUILD | WORM originals, sha256, evidence polygons rendered into the report |
| 10 | Repository + search + history | BUILD | Postgres + `pg_trgm`; product dedup on (manufacturer, brand, barcode) |
| 11 | Role-based access, secure auth | BUILD | Keycloak OIDC; RBAC enforced server-side per endpoint + jurisdiction row filter |
| 12 | Dashboards for officials | BUILD | Enforcement workbench: review queue, corrections, violation trends, rulepack admin |
| 13 | **Product listings / e-commerce** | PARTIAL | Officer pastes listing text + uploads gallery screenshots. Rule 6(10) variant (all Rule 6(1) declarations **except** month/year). **No crawler** — legally and operationally out of scope for v1 |
| 14 | Technical documentation | BUILD | `00`–`04` + OpenAPI + deployment runbook |

**Named non-goals** (say these out loud in the demo): verifying that a declared MRP is
the *true* MRP · net-content weighing · scripts beyond English/Hindi · automatic rule
publication · blockchain · Kubernetes · an end-to-end compliant/non-compliant classifier.

---

## 3. Legal baseline

### 3.1 Frozen facts (verified, buildable now)

Sourced from `source-extracts/GSR-2017-amendment-gazette.txt` pp. 11–12 and the
consolidated text. Restated here only because they are the values that go into
`tables.yaml`; `02` Part II is the authority.

- **Rule 7(2) Table-I** keyed to PDP area A (cm²), not net quantity:
  `A<50 → 1.0 / 1.5` · `50<A<100 → 1.5 / 3.0` · `100<A<500 → 2.5 / 4.0` ·
  `500<A<2500 → 4.0 / 6.0` · `2500<A → 6.0 / 6.0` (second value = blown/formed/molded).
  **Table-II omitted.**
- **Rule 7(4)** area excludes top, bottom, can flanges, bottle/jar shoulders and necks.
  Rectangular = h × w of the PDP side · Cylindrical = **0.40 × height × circumference** ·
  Other = 0.40 × total surface.
- **Rule 7(1)** ≤ **10 cubic cm** may use an affixed card/tape as PDP (was 5 cm³ pre-2017).
- **Rule 7(3)** width ≥ ⅓ height, except `1`, `i`, `I`, `l`.
- **Rule 7(5)** 7(1)–(4) do not apply where another law requires the same information —
  **except** net weight, retail sale price, expiry/best-before/use-by, consumer care.
- **Rule 8** clear space around the quantity declaration: ≥1× numeral height above/below,
  ≥2× left/right.
- **Rule 3** chapter inapplicable to: >25 kg or >25 L · cement/fertilizer/farm produce in
  bags >50 kg · **industrial or institutional consumers**.
- **Rule 26** *nothing in these rules applies* where net ≤10 g / 10 ml (**tobacco carved
  out**) · restaurant/hotel fast food · DPCO 2013 formulations (not medical devices
  declared as drugs) · thread in coil to handloom weavers.
- **Rule 6(1)(e)** MRP must state inclusive of all taxes and be **rounded to the nearest
  rupee or 50 paise**; four illustration forms are permitted (`MRP Rs. xx.xx incl. of all
  taxes`, etc.).
- **Rule 6(1)(ll)** unit sale price form is quantity-tiered: per g (<1 kg) / per kg (≥1 kg)
  / per cm (<1 m) / per meter (≥1 m) / per number / per ml (<1 L) / per litre (≥1 L).
- **Rule 6(10)** e-commerce: all Rule 6(1) declarations **except** month/year of
  manufacture or packing.
- **Rule 9(3) proviso (2017)** inner package needs no declarations if the outer package
  carries them all.

### 3.2 Errors this plan corrects

Carried here so nobody re-imports them from the superseded spec: net-quantity-keyed font
table (repealed 2017) · flat 2 mm embossed minimum · separate numeral/letter thresholds ·
cylindrical PDP as 40% of total surface · Rule 26 read as a unit-price-only exemption ·
missing Rule 3(c) · missing MRP rounding rule · 5 cm³ instead of 10 cm³ · four-state
verdicts.

### 3.3 Open legal questions — owned and dated

| # | Question | Blocks | Owner | Due |
|---|---|---|---|---|
| L1 | `<` vs `≤` at every Table-I boundary — the gazette text layer shows strict inequalities with gaps at A=50/100/500/2500 | Rule 7(2) verdicts near boundaries | legal pair | Wk 1 D3 |
| L2 | Devanagari letter height — shirorekha included? | Rule 7(2) on Hindi declarations | legal pair | Wk 1 D5 |
| L3 | Instruments after 2021-10-31 (2022 QR, 2023 garments, 2025 medical devices, 2026) — walk the ledger to newest | Rulepack currency claim | legal pair | Wk 2 |
| L4 | Rule 7(5) × FSSAI boundary for food articles | Applicability gate A3 | legal pair | Wk 2 |
| L5 | Qualified reviewer substitute | Rulepack sign-off | tech lead | Wk 1 D2 |

**Policy while open:** any rule touching an open question ships with
`verdict_ceiling: INDETERMINATE` — it produces evidence and a measurement, never a FAIL.
L1 additionally gets a **guard band**: measurements within ±1 combined-uncertainty of a
boundary return `INDETERMINATE` regardless.

---

## 4. Workstreams

Dependencies are hard. Nothing downstream starts on a guess about an upstream contract.

### W1 — Rulepack & legal ledger *(no dependencies; starts day 1)*
Build `rules.yaml` + `tables.yaml` + `checks.py` + amendment ledger + per-rule gazette
citation (file, page, sha256) + effective dates + rulepack hash + quarantine/approval flow.
**Done when:** 14 rules reviewed by two people with citations; every rule has ≥3 fixtures
(pass, fail, indeterminate); `pytest tests/rules/` green; rulepack hash printed at boot.

### W2 — Capture & evidence *(no dependencies)*
PWA guided capture, surface-coverage model, blur/glare/perspective gates, direct upload
with hashing, WORM original store, evidence-polygon viewer, barcode/QR read.
**Done when:** a 5-surface capture of an unseen product completes on a mid-range Android
browser in <90 s and every stored image hash verifies.

### W3 — OCR & extraction *(needs W2 contract only)*
PaddleOCR worker (en + Devanagari), token geometry preserved, candidate extractors for
each declaration, the disambiguation layer of §4.1, unit/date/money normalization →
`ExtractedLabel`.
**Done when:** field-level precision/recall measured on the gold set (§7); every extracted
field carries source token IDs, a score and the runner-up margin; and re-running the same
image twice produces byte-identical output.

### W4 — Verifier *(needs W1 + W3)*
Seven-stage pipeline (applicability → evidence sufficiency → presence → format →
semantics → typography → placement), six-state verdicts, uncertainty policy, execution
manifest.
**Done when:** a scan missing the back panel returns `INDETERMINATE` for back-panel
declarations and never `FAIL`; manifest replays a run byte-identically.

### W5 — Typography & measurement *(needs W3; two phases)*
**5a, calibration-free — build first:** Rule 7(3) width/height ratio · Rule 8 clear space ·
Rule 9(1)(b) contrast · Rule 9(4) script. Pure pixel ratios, no marker.
**5b, absolute mm:** ISO ID-1 / AprilTag coplanar fiducial → homography → rectified glyph
height → interval with 95% CI → Table-I lookup. Curved surfaces abstain.
**Done when:** 5a runs on any existing photo; 5b measurement error ≤0.15 mm on a printed
calibration sheet across 20 samples, and abstains when the fiducial is non-coplanar.

### W6 — Repository, review workbench, reports *(needs W4)*
Product dedup, search/filter, inspection history, officer correction flow (append-only
revisions), PDF/DOCX from one verdict object, report hash.
**Done when:** an officer corrects a mis-extracted MRP, re-runs, and both runs are
retained and diffable; PDF and DOCX contain identical findings and the rulepack hash.

### W7 — Auth, RBAC, dashboards *(needs W6 schema)*
Keycloak OIDC, four roles, server-side enforcement + jurisdiction row filter, audit log,
enforcement dashboards, rulepack admin with quarantine queue.
**Done when:** the RBAC matrix test (every role × every endpoint) passes with correct
200/403 and no endpoint relies on UI hiding.

### W8 — E-commerce variant *(needs W4; smallest workstream)*
Listing-text paste + screenshot upload, Rule 6(10) rule subset, mode flag on the report.
**Done when:** the same package evaluated in both modes differs only by the month/year rule
returning `NOT_APPLICABLE`.

### 4.1 The deterministic disambiguation layer *(replaces what a language model would do)*

The system ships **no language model.** Five jobs an LLM would conventionally absorb are
handled by small, auditable components instead. Each is a few hundred lines, has no model
weights, and returns the same answer every run.

| Job | Shipped mechanism | Library |
|---|---|---|
| Identify which text block is MRP / net qty / consumer care / address | **Lexicon + scored layout rubric** (below) | `rapidfuzz` |
| Read a heading mangled by OCR (`M.R.P`, `MRP:`, `MR.P`, `एम.आर.पी`) | Normalised edit distance against a curated multilingual synonym lexicon; accept at ≥0.85 similarity | `rapidfuzz` |
| Phrase a finding in plain language | **Message templates in `rules.yaml`** with typed slots, one per verdict state, in English and Hindi | `str.format` |
| "Which documents affect Rule 6?" | **SQL over the amendment operation ledger** — amendments are already parsed into typed ops against a rule tree, so this is a join, not a search | Postgres FTS |
| Propose patch operations from a new gazette | **Gazette grammar parser** (`02` §I.6) — the register is rigid: `for sub-rule (2) … shall be substituted` | `re` |

**The scored rubric.** For each declaration field, every OCR text block gets a score from
explicitly weighted, individually inspectable features:

| Feature | Example for `mrp` |
|---|---|
| Anchor keyword similarity | fuzzy match to lexicon `{MRP, M.R.P, Max Retail Price, Maximum Retail Price, एम.आर.पी, अधिकतम खुदरा मूल्य}` |
| Value pattern | currency symbol / `Rs.` adjacent to a decimal numeral |
| Co-text | `inclusive of all taxes`, `incl. of all taxes` within N tokens |
| Geometry | on the PDP; glyph height rank within the panel |
| Proximity | distance to the net-quantity block (they cluster) |
| Negative evidence | penalty for sitting inside the ingredients or marketing block |

The highest-scoring candidate wins **only if it clears an absolute floor and beats the
runner-up by a margin**. Otherwise the field is `INDETERMINATE` and an officer confirms it
in the review workbench. Weights live in `rules.yaml`, are tuned on the gold set, and are
printed in the evidence panel — so "why did you think that was the MRP?" has a numeric
answer, not a shrug.

**Optional v2, still not an LLM:** if the rubric plateaus, train logistic regression or a
small gradient-boosted tree on the same features. Ships as a few KB of coefficients,
inspectable, deterministic. Not needed for v1 and explicitly out of Week 1–5 scope.

**What is lost by having no LLM:** recall on unusual or badly damaged labels. Those become
`INDETERMINATE` — a correct abstention, not a wrong finding. Nothing about correctness,
citation or measurement depends on a language model.

---

## 5. Rulepack v1 — the 14 rules, plus 3 gates

Gates run **before** any rule. A gate that fires ends the evaluation with
`NOT_APPLICABLE` and a cited reason — this is what prevents false accusations.

| ID | Gate | Rule | Effect |
|---|---|---|---|
| A1 | Bulk / industrial | 3(a)(b)(c) | Chapter II not applied |
| A2 | Small pack / fast food / DPCO / thread | 26 | **All rules** not applied (tobacco excluded from (a)) |
| A3 | Other-law overlap | 7(5) | 7(1)–(4) skipped except net wt, RSP, expiry, consumer care |

| ID | Check | Rule | Type | Phase |
|---|---|---|---|---|
| R01 | Manufacturer/packer/importer name + complete address | 6(1)(a) | presence | W1 |
| R02 | Common or generic name | 6(1)(b) | presence | W1 |
| R03 | Net quantity in standard units | 6(1)(c) | presence | W1 |
| R04 | Month & year of manufacture/packing/import | 6(1)(d) | presence | W1 |
| R05 | Retail sale price | 6(1)(e) | presence | W1 |
| R06 | Consumer care name, address, phone, e-mail | 6(1)(f) | presence | W1 |
| R07 | Country of origin (imported goods) | 6 | presence | W1 |
| R08 | MRP form + inclusive-of-taxes + rounding to Re 1 / 50 p | 6(1)(e) | format | W1 |
| R09 | Net quantity numeral + canonical SI unit | 6(1)(c) | format | W1 |
| R10 | Date form (MM/YYYY or month name + year) | 6(1)(d) | format | W1 |
| R11 | Unit sale price tier form | 6(1)(ll) | format | W1 |
| R12 | Address contains PIN code (Explanation I) | 10(1) | format | W1 |
| R13 | Letter width ≥ ⅓ height | 7(3) | ratio | W5a |
| R14 | Quantity clear space ≥1× / ≥2× | 8 | ratio | W5a |
| R15 | RSP & net-qty numeral contrast | 9(1)(b) | ratio | W5a |
| R16 | Declarations in Hindi or English | 9(4) | classify | W5a |
| R17 | Minimum height per Table-I ← PDP area per 7(4) | 7(2) | calibrated | W5b |

Cross-field: **R19** unit sale price ≈ MRP ÷ net quantity within tolerance →
`REVIEW_REQUIRED` on mismatch, never auto-FAIL.

Deferred to v2 with a written reason: R18 (7(1) card/tape ≤10 cm³ — needs volume input),
R20 (6(3) sticker over MRP — needs a tamper detector).

---

## 6. Schedule and gates

Five weeks. A gate is not a status meeting — if its criteria fail, the following week's
scope is cut, not the criteria.

| Wk | Focus | Workstreams | **Gate to pass** |
|---|---|---|---|
| 1 | Legal + contracts | W1, W2 start | Rulepack v1 signed by two reviewers with citations; **all rule fixtures written before any UI exists**; `ExtractedLabel` + verdict schema frozen |
| 2 | Capture + OCR | W2, W3 | End-to-end photo → OCR tokens → evidence overlay on a real package; L3 ledger walked to newest instrument |
| 3 | Verifier | W4, W5a | Six-state verdicts on 10 gold packages; the missing-panel case returns `INDETERMINATE`; ratio checks producing real findings |
| 4 | Measurement + reports + review | W5b, W6, W7 | Rule 7(2) verdict with a CI and a gazette citation on-screen; PDF + DOCX export; officer correction round-trip; RBAC matrix green |
| 5 | Hardening | W8, eval, drills | Eval harness numbers published; adversarial set run; **offline drill** (gov source unreachable → cached rulepack still serves); backup/restore; rehearsal on an unseen product |

**Freeze at end of Week 5:** rulepack version, OCR weights, container digests. The finale
is spent on integration and reliability, not model changes.

---

## 7. Evaluation

Three datasets, held separately, none used for tuning the one it evaluates.

| Set | Size (min) | Purpose |
|---|---|---|
| Gold | 40 real packages, hand-annotated | Field-level extraction P/R; verdict correctness |
| Calibration | 20 printed sheets, known glyph heights | Measurement error and CI coverage |
| Adversarial | 15 constructed cases | Missing panel · glare over MRP · repealed-table trap · exempt small pack · bulk pack · Hindi-only label · MRP sticker · curved bottle |

Acceptance thresholds for v1 — a check that misses its bar ships with
`verdict_ceiling: INDETERMINATE` rather than being cut:

| Metric | Bar |
|---|---|
| Presence-check recall on mandatory fields | ≥ 0.90 |
| **False FAIL rate on compliant gold packages** | **≤ 0.02 — the number that matters most** |
| Glyph height error (calibration set) | ≤ 0.15 mm |
| CI coverage (true value inside stated interval) | ≥ 0.95 |
| Applicability gates on exempt packages | 100% — a gate miss is a release blocker |

---

## 8. Risk register

| Risk | L | Impact | Mitigation |
|---|---|---|---|
| Repealed thresholds reach `rules.yaml` | Med | Fatal to credibility | §1 disposition; every threshold cites gazette page + hash; one rule authority |
| Uncalibrated mm measurement is challenged | High | Flagship feature discredited | Ship 5a ratio checks first; 5b always emits a CI; guard band + abstention near boundaries |
| Curved packages dominate the demo shelf | Med | Coverage looks thin | Explicit abstention path with a stated reason; choose flat cartons for the primary demo |
| OCR fails on Devanagari declarations | Med | Half of Rule 9(4) unusable | Language detection per token; abstain rather than mis-extract; L2 blocks Hindi height verdicts |
| A 2026 amendment lands mid-build | Low | Currency claim breaks | Open-ended ledger + quarantine queue; **an unapproved amendment sitting in quarantine is a demo asset, not a defect** |
| Scope creep into "misleading declarations" | High | Unfalsifiable claims | Named non-goal in §2; report footer states what was and was not checked |
| Two rival spec documents | **Now** | Wrong law shipped | §1, week 1 day 1 |

---

## 9. Definition of done

A build is demo-ready when all of these hold:

1. Every verdict on screen shows: outcome · measured value with interval · required
   threshold · rule and sub-rule · gazette file, page and hash · rulepack version and hash
   · the evidence crop it was computed from.
2. No verdict exists that a person cannot trace to plain Python they can read.
3. No language model exists in the deployed system. Field identification, report wording
   and source lookup all run on the deterministic components in §4.1.
4. A package photographed incompletely returns `INDETERMINATE`, never `FAIL`.
5. An exempt package (≤10 g, or >25 kg, or institutional) returns `NOT_APPLICABLE` with
   the exempting clause cited, before any declaration check runs.
6. The report exports to PDF and DOCX with identical findings and a content hash.
7. The system runs with the government source unreachable.
8. A newly discovered notification is visible in quarantine, unapproved.
