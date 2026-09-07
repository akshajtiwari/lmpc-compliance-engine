# Legal Metrology Compliance System — Architecture

**Audience:** whole team, plus anyone evaluating the design.
**Companion docs:** `00-TEAM-BRIEF.md` (summary), `02-ENGINEERING-SPEC.md` (implementation detail).

---

> **Status, 2026-09-07.** This architecture has been built and validated against live
> data: 48 gazette instruments across 3 rule families, 140 real product photographs, 2,940
> rule evaluations. It survived — with 16 corrections, five of them architectural. The
> implementation-level document is [`02-BUILD-SPEC.md`](02-BUILD-SPEC.md); the corrections
> are catalogued in its Part M. Where this document and the spec disagree, **the spec is
> authoritative.**
>
> The five architectural corrections, none of which was visible before real data:
> instrument identity must include the **year** (G.S.R. numbers restart annually and
> collide); rule families must be resolved **transitively** or one chain fragments into
> several; **effective dates** must gate every check and every table version, or a 2016
> package is judged by 2018 law; a corrupt download must not kill a build; and absence of
> a declaration may only be a violation when the capture flow **asserted** that every
> surface was photographed.

## 1. Problem restated in engineering terms

We are asked to decide a **legal question** (does this package comply with the LMPC
Rules, 2011?) from **physical evidence** (a photograph) using a **moving target**
(a body of law amended ~15 times since 2011 and still changing in 2026).

Three distinct hard problems, and they must not be collapsed into one model:

| Problem | Nature | Correct tool |
|---|---|---|
| What does the label say? | Perception, probabilistic | OCR + vision |
| What does the law require? | Legal, versioned, discrete | Curated rulepack |
| Does (1) satisfy (2)? | Deterministic comparison | Plain code |

Almost every naive design fails by handing all three to one model. We ship **no language
model at all** — the problem statement asks for *rule-based* checking, and that is exactly
what runs.

---

## 2. What we verified about the source material

These are measured facts, not assumptions. They drive the design.

### 2.1 The government site

| Property | Finding | Consequence |
|---|---|---|
| TLS | Certificate chain **expired**; plain `curl` fails | Cannot use a normal HTTPS client |
| PDF links | Written as `http://` but **port 80 does not answer** | Must rewrite scheme to `https` |
| Speed | 17 s for a 2.4 MB PDF | Unusable synchronously |
| Reliability | Multiple outright failures under light sequential load | Needs retry + backoff + quarantine |

**Conclusion: inference must never touch this host.** Ingestion is an offline,
asynchronous, human-reviewed pipeline.

### 2.2 The corpus is mixed, split by era

| Document | Pages | Producer | Text layer? |
|---|---|---|---|
| Base PCR 2011 | 83 | OmniPage CSDK 15.5 | **No — pure scan** |
| Amd 2011 (1st) | 1 | none | No |
| Amd 2011 (3rd) | 2 | DPE Build 5656 | Yes |
| Amd 2012 | 9 | none | No |
| Amd 2013 | ? | none | No |
| Amd 2015 | 6 | none | No |
| Amd 2017 | 14 | GPL Ghostscript 9.06 | Yes |
| Amd 2021 | 4 | iTextSharp | Yes |
| Amd 2022 (Mar) | 3 | iTextSharp | Yes |
| Amd 2022 (QR) | 3 | iTextSharp | Yes |

Roughly 50/50. **Classify each file; never assume.**

### 2.3 Bilingual layout

- Base 2011 scan: Hindi pp. 1–~41, English pp. ~42–83. Clean, high-contrast type —
  very OCR-friendly.
- Digital amendments: Hindi block then English block *within* the same short document.
- **Hindi extracts as mojibake** from the text-layer PDFs (legacy non-Unicode gazette
  font). English extracts perfectly.

**Conclusion: work from the English text. Do not build a Hindi NLP pipeline for the
law.** (Hindi OCR is still needed for *package labels* — a different problem.)

### 2.4 A consolidated text already exists

Contrary to our initial assumption:

| Source | Pages | Form | Note |
|---|---|---|---|
| `legalmetrologymh.in` | 31 | Word → PDF, **English only**, 67k chars extractable | "As amended up to GSR dt. 31.10.2021" |
| `thc.nic.in` | 54 | Text layer | Consolidated |
| DoCA "all amendments" compilation | — | Official | ~Jan 2025 cut-off |

**This removes the need to OCR the 83-page bilingual scan to get started.** Use a
compilation as the *baseline*, then diff every instrument published after its cut-off.
A compilation is a starting point, never current law.

### 2.5 The law has moved well past 2022

Amendments exist through 2026, including:

- Second Amendment Rules 2025, G.S.R. 881(E) — pan-masala exception, **commenced 1 Feb 2026**
- G.S.R. 128(E) 2026 — country-of-origin filter for e-commerce
- Second Amendment 2026 — substitutes that provision, **effective 1 Jul 2027**
- Third Amendment Rules 2026, G.S.R. 418(E) — immediate commencement

Plus a **draft** 2025 country-of-origin proposal that was never notified in that form.

This forces the updater to distinguish: draft vs notified · publication date vs
commencement date · new obligation vs substitution vs omission vs corrigendum ·
compilation vs later instrument · rule vs advisory/FAQ/SOP.

**"Latest PDF wins" is provably wrong.**

### 2.6 Two structural gifts

**Every notification carries a `Note:` footer** naming the principal rules and the
*last* amendment:

> *The principal rules were published … vide G.S.R. 202(E), dated 7 March 2011 and was
> last amended vide notification G.S.R. 226(E), dated 28 March 2022.*

That is a machine-readable **linked list**. Walk it backwards to prove your amendment
chain has no gaps.

**Amendments use a rigid formal grammar:**

> *In the said rules, in rule 7, (i) for sub-rule (2), the following sub-rule shall be
> substituted, namely:— … (iv) Table II shall be omitted;*

This parses cleanly into patch operations (`insert`, `substitute`, `omit`, `renumber`,
`correct`, `commence`, `expire`).

### 2.7 A trap we hit ourselves

The 2017 gazette's own text layer renders `A ≤ 50` as `A < 50` — the `≤` glyph is lost.
**Boundary conditions must be human-verified.** This alone justifies keeping automated
rulepack publication out of the design.

---

## 3. System architecture

```
                    LEGAL CONTENT PLANE  (offline, asynchronous, human-gated)
    ┌──────────────────────────────────────────────────────────────────┐
    │  DoCA site  ·  e-Gazette  ·  India Code  ·  state LM portals      │
    │                          │                                        │
    │                   watcher + quarantine                            │
    │                          │                                        │
    │         classify PDF → extract/OCR → amendment ledger             │
    │                          │                                        │
    │              human legal review  →  signed rulepack release       │
    └──────────────────────────┬───────────────────────────────────────┘
                               │  (immutable, versioned, hash-pinned)
                               ▼
    ┌──────────────────── SHARED BACKEND ──────────────────────────────┐
    │                                                                   │
    │  API + auth ──── job queue ──── image / OCR workers               │
    │      │                              │                             │
    │      │                       structured extractor                 │
    │      │                              │                             │
    │      └──────────── DETERMINISTIC RULE ENGINE                      │
    │                                     │                             │
    │  PostgreSQL ◄──── evidence + verdicts ────► MinIO (WORM)          │
    │      │                              │                             │
    │  audit log                   PDF / DOCX renderer                  │
    └──────┬──────────────────────────────────────────┬────────────────┘
           │                                          │
           ▼                                          ▼
   Capture app (PWA)                        Enforcement console (web)
```

**Key property: the two planes are decoupled.** A government-site outage cannot affect
a single inspection, because inference reads only cached signed rulepacks.

### 3.1 Why not a separate "edge" tier

Rejected. It adds deployment failure modes without improving the demo. Instead:
presigned direct-to-object-store uploads, resumable multipart, on-device capture
validation, and an API endpoint close enough for the demo.

---

## 4. Client split — corrected

The original plan had "live app" vs "passive dashboard". The dashboard is **not**
passive. It owns:

- Low-confidence review queues
- Officer corrections to extracted values
- Side-by-side evidence inspection
- Rulepack drafting → review → approval → activation → rollback
- Product-history comparison
- Report signing and case disposition
- Audit and model-quality monitoring

It is an **enforcement workbench**.

### 4.1 Platform decision: PWA, not Android-only

| | Android native | **PWA (chosen)** |
|---|---|---|
| Problem statement fit | "mobile" only | "web **and/or** mobile" ✓ |
| Judge can open it | needs install | any device, one URL ✓ |
| Camera control | excellent | good (`getUserMedia`) |
| Build cost | weeks | days ✓ |
| Offline | excellent | adequate (service worker) |

The guided-capture UX matters far more than native camera APIs. Revisit only if
frame-rate profiling proves the web camera path inadequate.

---

## 5. The rules layer

### 5.1 Decision: curated rulepack, with retrieval as a research aid only

| Approach | Verdict | Why |
|---|---|---|
| RAG over PDFs at inference | **Rejected for verdicts** | Retrieves repealed amendments, Hindi copies, drafts; misses provisos and commencement clauses; hallucinated citations; non-reproducible; dies when the host is slow |
| One-time hand-built JSON | **Rejected** | Silently goes obsolete; loses amendment history, effective dates, reviewer identity, reproducibility |
| **Versioned rulepack + review process** | **Chosen** | Auditable, citable, reproducible, testable |
| Retrieval over source PDFs | **Kept, scoped** | "Show me documents affecting Rule 6" — for humans, never for verdicts |

### 5.2 Ingestion pipeline

```
discovered → quarantined → parsed → consolidated
          → technically reviewed → legally reviewed → signed → active
```

1. **Watch, don't trust.** Daily/weekly fetch of the HTML index; store raw HTML,
   headers, timestamp, TLS result, SHA-256; diff the link inventory; create
   `source_candidate` records.
2. **Prefer better hosts.** e-Gazette → India Code → state portals → DoCA → manual
   upload. Never auto-promote a broken-TLS or HTTP-only source; cross-match G.S.R.
   number, date and content against a second official source.
3. **Classify before OCR** (`pdfinfo`, `pdffonts`, `pdftotext -layout`, `pdfimages -list`)
   into digital / scanned / mixed / corrupt. Digital → PyMuPDF. Scanned → OCRmyPDF
   with deskew, `hin+eng`. Always keep page images and token coordinates so a citation
   can open the exact region.
4. **Amendment operation ledger** — each instrument becomes typed operations against a
   rule tree, with source page, region, and hash.
5. **"Law as at date" snapshots** — immutable releases (`lmpc-2026.05.29-r1`) built by
   applying reviewed operations, with bitemporal fields (`valid_from`/`valid_to`,
   `recorded_at`/`superseded_at`).

**A grammar parser proposes operations. A human accepts them.** Gazette language is a rigid
register (`for sub-rule (2), the following … shall be substituted`) and parses with regular
expressions — see `02-ENGINEERING-SPEC.md` §I.6. No model is involved, so a proposal can
never be invented.

### 5.3 Date basis is per-rule, not global

Do not assume one `as_of` date. Each rule declares its basis: `inspection_date`,
`packing_date`, `import_date`, `listing_date`, `sale_date`, `commencement_transition`,
or `legal_reviewer_required`. Where interpretation is unclear, block automated failure.

---

## 6. The extraction layer

```
A. Capture validation   blur, glare, exposure, perspective, surface coverage
B. Geometric processing rectification, panel segmentation, marker detection
C. OCR routing          PaddleOCR; script detection per region
D. Candidate generation regex + fuzzy lexicon + scored layout rubric (04 §4.1)
E. Normalization        units, dates, currency — preserving raw evidence
```

Output is a structured `ExtractedLabel` where **every field carries its source token
polygon, image ID, and confidence** — never a bare string. If a value cannot be traced
back to visible pixels, it does not exist.

---

## 7. The verification layer

### 7.1 Staged, in this order

| Stage | Question | Possible verdicts |
|---|---|---|
| 0 Applicability | Is this package governed by this rule? | `PASS` / `NOT_APPLICABLE` |
| 1 Evidence sufficiency | Did we capture enough to conclude anything? | `PASS` / `INDETERMINATE` |
| 2 Presence | Are all mandatory declarations present? | `PASS` / `FAIL` / `INDETERMINATE` |
| 3 Syntax | Are they well-formed? | `PASS` / `FAIL` |
| 4 Semantics | Are values plausible and internally consistent? | `PASS` / `FAIL` / `REVIEW_REQUIRED` |
| 5 Typography | Height, width ratio, contrast | `PASS` / `FAIL` / `INDETERMINATE` |
| 6 Placement | On the PDP? Clear space respected? | `PASS` / `FAIL` / `INDETERMINATE` |

Stages 0 and 1 are what stop false accusations, and they were missing from the
original plan.

### 7.2 Uncertainty policy

For threshold `T` and measured 95% interval `[L, U]`:

```
PASS           if L ≥ T
FAIL           if U < T
INDETERMINATE  if L < T ≤ U
```

For absence:

```
FAIL only if:  rule applicable
           AND required surface coverage complete
           AND image quality acceptable
           AND no qualifying candidate found
           AND absence-confidence threshold met
otherwise      INDETERMINATE or REVIEW_REQUIRED
```

### 7.3 Product-level status

Never display a bare "COMPLIANT" when only 10 of many rules are implemented:

`NON_COMPLIANT_CONFIRMED` (officer-confirmed) · `NON_COMPLIANT_PROVISIONAL`
(machine, awaiting review) · `COMPLIANT_WITHIN_SCOPE` · `INCOMPLETE_ASSESSMENT` ·
`OUT_OF_SCOPE`.

---

## 8. Physical measurement

### 8.1 Build the calibration-free checks first

Two requirements are **pure pixel ratios** — no marker, no mm, no uncertainty:

- **Rule 7(3)** — letter width ≥ ⅓ of its height (except `1`, `i`, `I`, `l`)
- **Rule 8** — clear space around the quantity declaration: ≥ 1× numeral height
  above/below, ≥ 2× left/right

These are genuine violations, detectable on any existing photo. Ship them first.

### 8.2 Absolute mm — coplanar fiducial

Threshold depends on **PDP area**, and Rule 7(4) gives the formulas outright:

| Package shape | PDP area |
|---|---|
| Rectangular | height × width of that side |
| Cylindrical / near-cylindrical | **40%** × height × circumference |
| Any other shape | **40%** of total surface area |

Pipeline: place a 40–60 mm AprilTag/ArUco card coplanar with the declaration → detect
corners → correct lens distortion → plane homography → rectify to metric coordinates →
segment glyphs → measure → aggregate three frames → report an interval.

**Critical nuance:** an OCR bounding box is *not* legal letter height. It includes line
spacing, matras, ascenders and descenders. For Devanagari the shirorekha makes
Latin-style cap-height meaningless. The measurement convention must be documented and
legally reviewed.

### 8.3 Calibration hierarchy

| Method | Role |
|---|---|
| Coplanar AprilTag + ruler card | **Primary** — defensible measurement |
| Known object (e.g. a bank card) | Secondary — provisional |
| SKU dimensions from a database | Cross-check only |
| User-entered dimensions | Screening only |
| ARCore/ARKit depth | Surface geometry only — accurate range ~0.5–5 m, far coarser than mm lettering |
| Unscaled photograph | **No measurement** — typography must be `INDETERMINATE` |

Targets (to be benchmarked, not promised): <5% relative error at p95 on flat matte
panels with a coplanar marker; <10% with a non-coplanar reference.

Always render as `2.18 mm (95% CI 2.06–2.30, 40 mm coplanar AprilTag)` — never a bare
number.

### 8.4 Curved packages

A single homography is invalid on a bottle. For the hackathon: support flat cartons and
near-flat pouch regions, and **demonstrate graceful abstention on a bottle**. Abstaining
correctly scores better than a confident wrong number.

---

## 9. Reproducibility

Any verdict must be re-derivable years later. Every scan records an **execution
manifest**: input image hashes, rulepack release ID + hash, model names + weight
hashes, container digest, parameters, timestamp, operator.

Re-evaluating under a newer rulepack creates a **new run**; it never mutates the old
one. A 2026 amendment must not silently change a 2025 case.

Evidence integrity: client-side SHA-256 at capture, WORM object storage, append-only
revisions, signed report manifests. (This establishes *technical* integrity; *legal*
admissibility needs more and is out of scope — say so.)

---

## 10. Technology stack

| Layer | Choice | Reason |
|---|---|---|
| Capture client | **PWA** — `getUserMedia`, service worker | Fits "web and/or mobile"; any judge device |
| Console | React + TanStack Query | Standard, fast to build |
| Backend | FastAPI + Pydantic + SQLAlchemy, **modular monolith** | One deployable; Pydantic doubles as the schema contract |
| OCR | **PaddleOCR** (English + Devanagari) | Best multilingual accuracy/effort ratio; ML Kit for on-device preview |
| Gazette OCR | OCRmyPDF + Tesseract `hin+eng` | Only for the ~50% scanned instruments |
| Geometry | OpenCV + AprilTag | Homography, distortion, marker pose |
| Database | PostgreSQL 16 (JSONB + `tstzrange`) | Bitemporal rule validity, no second store needed |
| Objects | MinIO (S3 API) | Local, WORM-capable, presigned uploads |
| Queue | Redis + Dramatiq | Simpler than Celery |
| Vector store | **pgvector**, only for source retrieval | Never in the verdict path |
| Auth/RBAC | Keycloak (OIDC) | Real RBAC without hand-rolling it |
| Reports | WeasyPrint (PDF) + docxtpl (DOCX) | "PDF and editable formats" |
| Deploy | Docker Compose | **No Kubernetes** |

---

## 11. Evaluation

Three datasets, not one:

1. **Gold package set** — real packages, hand-annotated per field, with ground-truth
   compliance judgements.
2. **Physical typography calibration set** — printed charts at known heights, verified
   with callipers/loupe.
3. **Synthetic perturbation set** — programmatically degraded (blur, glare, rotation,
   occlusion, sticker overlay) to measure graceful degradation.

Metrics: per-field precision/recall · per-rule confusion including the `INDETERMINATE`
class · measurement error distribution · **abstention rate** (a feature, not a failure).

**Optimize FAIL precision above all.** A false violation against a real manufacturer is
far more costly than a missed one. Report the "rule of three" honestly: zero false
positives in *n* samples only bounds the rate at roughly 3/*n*.

---

## 12. Scope

**In:** physical retail pre-packaged commodities · flat cartons and near-flat pouches ·
English + Hindi · guided multi-surface capture · MRP, net quantity, responsible
party/address, month & year, consumer care, generic name, country of origin ·
presence, syntax, internal consistency, selected placement · Rule 7 typography on
calibrated surfaces · explicit abstention elsewhere.

**Stubbed (label as future scope):** scripts beyond English/Hindi · automated
curved-surface measurement · external verification of manufacturer identity or true MRP ·
net-content measurement · e-commerce crawling · multi-device offline conflict resolution ·
automatic amendment consolidation · government-certificate report signing.

**Cut entirely:** blockchain · Kubernetes · from-scratch OCR training · end-to-end
compliance image classifier · runtime RAG verdicts · Elasticsearch · 3D reconstruction ·
all LMPC rules and exemptions · iOS native · unsupervised rule publication.

---

## 13. Judge attack surface

| Attack | Answer |
|---|---|
| "How do you know this is current law?" | Source inventory, amendment ledger, effective dates, reviewer approval, rulepack hash |
| "That PDF was only a draft." | `draft` vs `notified` classification and promotion controls |
| "The back wasn't photographed." | `INDETERMINATE` — absence is never inferred from incomplete coverage |
| "How can a photo measure millimetres?" | Coplanar calibrated marker, homography, repeated frames, error interval |
| "What about curved bottles?" | Validated local-surface workflow, or explicit abstention |
| "The model hallucinated that field." | There is no language model. Field choice is a scored rubric over inspectable features, every field references visible token polygons, and a weak winning margin abstains |
| "MRP exists — but is it correct?" | Syntax and internal consistency ≠ external factual truth. We say which we checked |
| "What about exemptions?" | Applicability stage runs before any declaration check |
| "Can I reproduce this next year?" | Execution manifest: inputs, rulepack, weights, container digest |
| "Can an officer alter evidence?" | WORM original, hashes, signed manifest, append-only revisions |
| "What if the government site is down?" | Inference uses cached signed rulepacks; ingestion is asynchronous |
| "Can a new amendment change an old case?" | No. Old evaluations keep their rulepack; re-evaluation is a new run |

The dangerous questions are not about OCR accuracy. They are about **legal
applicability, incomplete evidence, physical scale, versioned law**, and whether the
system knows the difference between *not found*, *not valid*, and *not determinable*.
