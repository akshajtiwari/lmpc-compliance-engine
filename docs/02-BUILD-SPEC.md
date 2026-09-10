# Build Specification — Legal Metrology Compliance System

**Document ID:** LMPC-SPEC-002 · **Version:** 3.1 · **Status:** Approved for implementation
**Date:** 2026-09-08
**Supersedes:** v2.0; `archive/2026-09-engineering-spec-superseded.md`;
`archive/2026-09-technical-spec-superseded.md`

---

## 0. About this document

### 0.1 Purpose

This is the complete engineering specification. A team that has never seen the project
must be able to build every component from this document alone. Where a decision is
genuinely open it appears in **Part 25** with an owner and a date — nowhere else.

### 0.2 Requirement language

| Word | Meaning |
|---|---|
| **MUST** | Mandatory. A build that violates it is defective and CI fails. |
| **MUST NOT** | Prohibited. |
| **SHOULD** | Strongly recommended; deviation requires a recorded reason in the PR. |
| **MAY** | Optional. |

### 0.3 Provenance of numbers

Every threshold and latency figure here was **measured**, not estimated. Anything not
measured is marked `[ESTIMATE]`.

| Source | Scale |
|---|---|
| Live gazette corpus | 48 instruments, 3 rule families, 2011–2026 |
| Real product photographs | 140 products, 403 images, 4 categories |
| Rule evaluations executed | 2,700 |
| Synthetic labels | rendered at 300 DPI with exact known glyph geometry |
| Hardware | Ordinary laptop CPU. **Every timing here is a CPU figure** — an RTX 3050 was present but `onnxruntime` never actually used it (M.18) |

### 0.4 Contents

| Part | Subject | Owner |
|---|---|---|
| 1 | Product definition, personas, use cases | Product |
| 2 | Engineering principles | All |
| 3 | System architecture, client/server split, topology | Architecture |
| 4 | Domain model and data contracts | Backend |
| 5 | Law compiler subsystem | Compiler |
| 6 | Rulepack format and lifecycle | Compiler |
| 7 | Capture subsystem | Mobile |
| 8 | Vision and OCR subsystem | Vision |
| 9 | Extraction subsystem | Vision |
| 10 | Rule engine | Backend |
| 11 | Evidence, reporting, repository | Backend |
| 12 | HTTP API specification | Backend |
| 13 | Database schema and data lifecycle | Backend |
| 14 | Authentication | Platform |
| 15 | Authorisation and RBAC | Platform |
| 16 | Web console | Frontend |
| 17 | Mobile client and synchronisation | Mobile |
| 18 | Infrastructure, environments, configuration | Platform |
| 19 | Observability and service levels | Platform |
| 20 | Security | Security |
| 21 | Testing strategy | QA |
| 22 | Delivery plan and acceptance | Programme |
| 23 | Rule catalogue | Legal + Compiler |
| 24 | Defect register | All |
| 25 | Open questions | Named owners |
| A–E | Appendices: error codes, configuration, glossary | |

---

## Part 1 — Product definition

### 1.1 Problem

Under the Legal Metrology Act, 2009 and the Legal Metrology (Packaged Commodities) Rules,
2011, every pre-packaged commodity sold in India must bear prescribed declarations —
manufacturer's name and address, common name of the commodity, net quantity, month and
year of packing, retail sale price, consumer care details — in a prescribed manner,
including minimum letter heights and clear space around the quantity declaration.
Enforcement today is manual, sample-based and slow.

### 1.2 What this system does

Produces a **first-pass, evidence-backed, officer-reviewable** compliance assessment of a
packaged commodity from photographs, against the law **in force on the date of inspection**.

### 1.3 Explicit non-goals

| Not done | Why |
|---|---|
| Decide a case | Every output is a first-pass finding for an officer |
| Verify a declared MRP is the *true* MRP | Requires facts not on the label |
| Detect "misleading" declarations | Unfalsifiable from an image |
| Weigh net contents | Requires physical apparatus |
| Scripts beyond English and Hindi | Out of scope for v1 |
| Publish a rule change without human approval | Prohibited by design |
| Any large language model in the product | Problem statement specifies rule-based checking |

### 1.4 Personas

| Persona | Role code | Need | Device |
|---|---|---|---|
| Field Officer | `FIELD_OFFICER` | Capture correctly, often offline | Mid-range Android, 4 GB RAM, intermittent 4G |
| Reviewing Officer | `REVIEWING_OFFICER` | See evidence, correct, sign off, export | Desktop browser |
| Administrator | `ADMIN` | Users, jurisdictions, rulepack versions | Desktop browser |
| Auditor | `AUDITOR` | Read-only within scope | Desktop browser |
| Legal Reviewer | `ADMIN` + `legal_reviewer` | Approve amendment diffs against gazette pages | Desktop browser |

### 1.5 Use cases

**UC-1 Field inspection.** Officer photographs a package under guidance, supplies a scale
reference, submits. Within 15 s a verdict list appears with evidence crops.

**UC-2 Offline inspection.** As UC-1 with no connectivity. Queued locally under a
client-generated UUID; syncs idempotently on reconnect.

**UC-3 Review and finalise.** Reviewing officer corrects a mis-extracted field, re-runs,
overrides one verdict with a written reason, finalises. PDF and DOCX generated.

**UC-4 E-commerce listing.** Officer supplies listing text and gallery screenshots. The
Rule 6(10) subset is evaluated (all declarations except month and year of packing).

**UC-5 Amendment approval.** Watcher discovers a gazette notification; it is parsed and
quarantined; a legal reviewer confirms numeric boundaries against the page image and
approves; a new rulepack version publishes. Finalised reports are untouched.

**UC-6 Audit.** An 18-month-old report is reproduced: same rulepack hash, same law
version, same verdicts.

### 1.6 Success criteria

| # | Criterion | Measurement | Status |
|---|---|---|---|
| SC-1 | Guided capture ≤ 90 s on a mid-range Android browser | 20 timed trials | Not built |
| SC-2 | Verdict within 15 s p95 of upload completion | Server metric | On track (6.6 s measured pipeline) |
| SC-3 | ≥ 90 % of mandatory declarations identified on correctly captured packages | Labelled eval set | **~50 % — gap** |
| SC-4 | **Zero** `FAIL` without `coverage_asserted` | Alert metric | **0 / 2,700** |
| SC-5 | Every verdict cites clause, gazette page, rulepack hash | Automated assertion | Passing |
| SC-6 | An 18-month-old report reproduces byte-identically | Manifest replay | Design complete |
| SC-7 | Operates with the government source unreachable | Offline drill | Passing |

---

## Part 2 — Engineering principles

Each is enforced by code, covered by a test, and exists because its absence produced a
wrong legal conclusion. `M.n` references are to Part 24.

| # | Principle | Enforced by | Taught by |
|---|---|---|---|
| **P1** | The law is compiled, never read at runtime | No network client in the request path | — |
| **P2** | Instrument identity is (number, **year**) | `lawc.parse._key()` | M.8 |
| **P3** | Six verdicts, not two | `Verdict` enum; no boolean in the verdict path | — |
| **P4** | Absence requires asserted coverage | `coverage_asserted` gate in `presence()` | M.16 |
| **P5** | Different claims need different confidence | `LEGIBLE` / `ACCUSE` split | M.2, M.6 |
| **P6** | Measure what the rule names, or abstain | `glyph_segmentation` gate | M.15 |
| **P7** | Repealed law is retained and dated | `params.versions[]` | M.11 |
| **P8** | No language model in the product | Dependency policy + CI import check | — |
| **P9** | Repair locates a declaration, never reads one | `Token.repaired` refusal | M.17 |

**P1.** Gazette PDFs are build-time inputs. The deployed system executes a ~14 KB
hash-addressed rulepack. Retrieval at verdict time can surface a repealed amendment, a
Hindi rendition, or a draft that never commenced — and cannot be reproduced later.

**P2.** G.S.R. numbers restart annually. `G.S.R. 875(E)` is both the General Rules
amendment of 9 Sep 2016 and the breath-analyser amendment of 28 Nov 2025; both are cited
as predecessors by different instruments in the live corpus.

**P3.** A boolean return type anywhere in the verdict path is a defect.

**P4.** A third-party image label is not an assertion of coverage. *On 48 of 60 real food
products the price was never photographed.*

**P5.** One threshold for all claims produced either false accusations (set low) or silent
misses (set high).

**P6.** Rule 7(3) compares a letter's width to its own height. A detection box spans
ascenders, descenders and padding.

**P7.** A finding is reproducible only while the version that governed it exists in the
rulepack.

**P8.** CI MUST fail if `openai`, `anthropic`, `transformers`, `llama_cpp`, `langchain`,
or `sentence_transformers` appears in the runtime dependency tree.

**P9.** Respacing `4S.3s` into `4 S.3 s` let the parser consume `4`, call it rounded, and
pass a label declaring 45.30. A correction may only ever downgrade a `FAIL`.

---

## Part 3 — System architecture

### 3.1 Two independent machines

```
════════ BUILD TIME (offline, weeks apart) ════════

 gazette PDFs ─▶ Law Compiler ─▶ diff ─▶ human approval ─▶ RULEPACK (~14 KB, hashed)
                 lmpc.lawc                                        │
════════ RUN TIME (per scan, seconds) ════════════════════════════│════════

 Capture ─▶ API ─▶ Queue ─▶ OCR Worker ─▶ Extraction ─▶ Rule Engine ◀┘
 (client)                   (CPU; GPU optional)              │
                                                            ▼
                              Evidence · Verdicts · Report · Repository
```

### 3.2 Service topology

| Service | Runtime | Replicas (pilot) | Scaling signal | GPU |
|---|---|---|---|---|
| `api` | FastAPI / Uvicorn | 2 | CPU + RPS | No |
| `worker-ocr` | Python + ONNX Runtime | 2 | Redis queue depth | Optional |
| `worker-rules` | Python | 2 | Redis queue depth | No |
| `worker-reports` | Python + WeasyPrint | 1 | Redis queue depth | No |
| `web` | Next.js (SSR) | 2 | CPU | No |
| `postgres` | PostgreSQL 16 | 1 primary + 1 read replica | — | No |
| `redis` | Redis 7 | 1 | — | No |
| `minio` | MinIO / S3-compatible | 1 or managed | — | No |
| `keycloak` | Keycloak 25 | 1 | — | No |
| `lawc` | Python CronJob | on demand | schedule | No |

**A GPU is a nice-to-have on `worker-ocr`, not a requirement.** An earlier revision of
this document claimed the opposite. That claim was wrong: `onnxruntime` advertises
`CUDAExecutionProvider` even when the CUDA runtime libraries are absent, and session
creation then falls back to CPU with only a warning — so the figures recorded as "GPU"
were measured on CPU throughout (M.18). **CPU at 1.6 s/panel meets SC-2 with margin.**
The real cause of the original unbounded runtimes was feeding 64 MP frames to the
recogniser, fixed by `MAX_EDGE` (Part 8.2). Provision a GPU to raise `MAX_EDGE` or
throughput, not to make the system viable.

### 3.3 Request sequence — UC-1

```
Client            API           Redis      OCR Worker    Rules Worker      DB / S3
  │ POST /scans ──▶│              │             │              │              │
  │                ├ validate     │             │              │              │
  │                ├ put objects ─┼─────────────┼──────────────┼─────────────▶│
  │                ├ INSERT scan ─┼─────────────┼──────────────┼─────────────▶│
  │                ├ enqueue ────▶│             │              │              │
  │◀ 202 {scan_id} ┤              ├ ocr.job ───▶│              │              │
  │                │              │             ├ fetch ───────┼─────────────▶│
  │                │              │             ├ prepare+OCR  │              │
  │                │              │             ├ write tokens ┼─────────────▶│
  │                │              │◀ enqueue ───┤              │              │
  │                │              ├ rules.job ──┼─────────────▶│              │
  │                │              │             │              ├ layout       │
  │                │              │             │              ├ extract      │
  │                │              │             │              ├ evaluate     │
  │                │              │             │              ├ write ──────▶│
  │◀ WS scan.updated ─────────────┼─────────────┼── notify ────┤              │
  │ GET /scans/{id}▶│             │             │              │              │
  │◀ 200 detail ───┤              │             │              │              │
```

**Latency budget** (4 panels, `MAX_EDGE=1800`, **CPU** — see M.18):

| Stage | Target p95 | Measured |
|---|---|---|
| Upload → 202 | 2.0 s | `[ESTIMATE]` |
| OCR, 4 panels | 8.0 s | 6.4 s (1.6 s/panel) |
| Layout + extraction | 0.5 s | 0.2 s |
| Rule evaluation | 0.1 s | 0.04 s |
| **End to end** | **15 s** | — |

### 3.4 Decisions and rejected alternatives

| Decision | Chosen | Rejected | Reason |
|---|---|---|---|
| Rule representation | Compiled rulepack | RAG over PDFs | Non-reproducible; retrieves repealed text; cannot be cited |
| Backend shape | Modular monolith + workers | Microservices | Pilot scale; one deployable; no distributed transactions |
| OCR placement | Server-side | On-device | Evidence stays on controlled infrastructure; models update without a fleet-wide app release; a verdict computed on an uncontrolled device is not defensible |
| OCR runtime | RapidOCR (ONNX) | PaddlePaddle | 200 MB vs ~2 GB; identical model family |
| Field identification | Fuzzy lexicon + scored rubric | LLM / LayoutLM | P8; a rubric is explainable in court |
| Orchestration | Docker Compose | Kubernetes | Pilot scale; operational burden |
| Search | PostgreSQL + `pg_trgm` | Elasticsearch | Avoid a second datastore until latency demands it |
| Client | PWA | Native Android | Any device; no store review |
| Auth | Keycloak (OIDC) | Hand-rolled JWT | Departmental SSO must plug in without rework |

### 3.5 Why the work is split between client and server

A reasonable first assumption is that everything ships inside a phone app. It cannot, and
the problem statement itself is what rules it out. Six of its stated requirements are
impossible on an isolated device:

| Problem-statement requirement | Why it needs a server |
|---|---|
| "User-friendly **web** and/or mobile-based software application" | A web application *is* a server-side deployment |
| "Maintaining a **repository** of scanned products and compliance history" | A repository spanning officers cannot live on one handset |
| "Providing **dashboards** for enforcement officials" | Aggregation across inspections, officers and jurisdictions |
| "**Search and retrieval** facility for previously scanned products and reports" | Search over a shared corpus |
| "**Role-based user access** and secure authentication" | Roles are meaningless without a central authority; a device-local role is self-asserted |
| "Technical documentation describing software architecture and **deployment framework**" | A deployment framework is being asked for explicitly |

Three further reasons are ours, not the problem statement's:

1. **Evidence integrity.** A verdict computed on a device the inspected party's counterpart
   controls is not defensible. Originals are hashed on arrival and stored immutably
   server-side; the device never holds the authoritative copy.
2. **Rulepack currency.** When the law changes, a reviewer approves a diff and the new
   rulepack is live for everyone (Part 6.6). If rules lived on devices, every amendment
   would need an app release and a fleet-wide update — and old handsets would silently
   apply repealed law.
3. **Reproducibility.** SC-6 requires an 18-month-old report to reproduce byte-identically.
   That needs the rulepack, the model hashes and the execution manifest under one
   controlled configuration, not whatever version a particular phone happened to run.

**What the client does keep.** Capture, quality gates, the coverage assertion, offline
queueing and rendering — see Part 7 and Part 17. Field work continues with no
connectivity; scans queue locally and sync when the officer returns to signal. The
client holds **no legal logic**: no thresholds, no comparisons, no rule text.

**Why OCR is server-side rather than on-device.** It is technically possible via ONNX
Runtime Web, and was considered:

| | On-device | Server-side (chosen) |
|---|---|---|
| Model download | ~21 MB per handset, over mobile data | Once, into a container |
| Speed | Mid-range phone CPU, unmeasured | 1.6 s/panel measured |
| Model updates | Fleet-wide app update | Container redeploy |
| Evidence chain | Verdict computed on an uncontrolled device | Controlled infrastructure |
| Offline capture | Works either way — capture is local, evaluation is deferred | Works either way |

Nothing is lost offline: the officer still captures, and evaluation happens on sync.

**On-premises is supported.** "Server-side" does not mean "someone else's cloud". The
entire stack runs on a single departmental machine via Docker Compose (Part 18), with
MinIO for storage and PostgreSQL for data. See 3.6.

### 3.6 Deployment constraints

- MUST be deployable on-premises or on a MeitY/NIC-empanelled cloud.
- MUST NOT depend on a proprietary managed service unavailable in such an environment.
- Object storage MUST be S3-API compatible.
- Images MUST be reproducible from a pinned lockfile and a pinned base-image digest.

---

## Part 4 — Domain model and data contracts

Python is authoritative. TypeScript mirrors are generated from the OpenAPI document
(Part 12) and MUST NOT be hand-edited.

### 4.1 Verdict

```python
class Verdict(str, Enum):
    PASS = "PASS"; FAIL = "FAIL"; INDETERMINATE = "INDETERMINATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"; REVIEW_REQUIRED = "REVIEW_REQUIRED"
    SYSTEM_ERROR = "SYSTEM_ERROR"
```

| Verdict | Semantics | Automatic? |
|---|---|---|
| `PASS` | Requirement demonstrably met | Yes |
| `FAIL` | Requirement demonstrably violated | Only with asserted coverage, legible evidence, and confidence above the claim's threshold |
| `INDETERMINATE` | Evidence or law insufficient | Yes — the default under doubt |
| `NOT_APPLICABLE` | Rule does not govern this package, mode or date | Yes |
| `REVIEW_REQUIRED` | Lawful under one reading; a person decides | Yes |
| `SYSTEM_ERROR` | Defect in this system | Yes; MUST NOT read as a finding against a trader |

### 4.2 Token

```python
@dataclass
class Token:
    text: str
    x: int; y: int; w: int; h: int      # pixels in the RESIZED frame (Part 8.2)
    conf: float = 1.0                    # 0.0–1.0
    panel: str = "FRONT"                 # FRONT|BACK|SIDE_1|SIDE_2|TOP|BOTTOM
    cap_height_px: float | None = None   # h × CAP_RATIO — a documented bias
    src: frozenset = frozenset()         # provenance: source raw-region indices
    repaired: bool = False               # respaced or joined (P9)
```

**Invariants.** `w > 0`; `h > 0`; `0.0 ≤ conf ≤ 1.0`; `src` non-empty after layout
assembly. A token with `len(src) > 1` is composite and MUST NOT be used for any geometric
measurement (Part 10.4).

### 4.3 Scan

```python
@dataclass
class Scan:
    tokens: list[Token]
    captured_at: str = "YYYY-MM-DD"      # P7 — selects the governing law
    panels_captured: set[str] = {"FRONT"}
    coverage_asserted: bool = False      # P4 — set ONLY by the capture flow
    glyph_segmentation: bool = False     # P6
    mode: str = "PHYSICAL_PACKAGE"       # | ECOMMERCE_LISTING
    category: str = "GENERIC"
    buyer_type: str = "RETAIL"           # | INDUSTRIAL | INSTITUTIONAL
    is_imported: bool = False
    is_molded: bool = False
    other_law_requires_same_info: bool = False
    package_shape: str = "RECTANGULAR"   # | CYLINDRICAL | IRREGULAR
    px_per_mm: float | None = None       # None ⇒ millimetre checks abstain
    pdp_h_cm: float | None = None
    pdp_w_cm: float | None = None
    net_quantity_g: float | None = None
    net_quantity_ml: float | None = None
    capacity_cm3: float | None = None
    is_outer_package: bool = False
    outer_is_transparent: bool = False
```

### 4.4 Field

```python
@dataclass
class Field:
    kind: str
    text: str
    tokens: list[Token]
    score: float          # rubric total
    margin: float         # gap to nearest materially different candidate
    normalized: dict      # field-specific; includes "_features" for explainability
```

### 4.5 Field kinds

`mrp · net_quantity · mfg_date · consumer_care · manufacturer_block ·
country_of_origin · generic_name · unit_sale_price` — plus `brand_name` (non-mandatory,
used for deduplication).

### 4.6 Commodity categories

| Code | Legal significance |
|---|---|
| `FOOD` | FSSAI overlap; Rule 7(5) may apply |
| `COSMETIC` | No FSSAI overlap |
| `GENERIC` | Default |
| `CEMENT` `FERTILIZER` `FARM_PRODUCE` | Rule 3(b) at bags > 50 kg |
| `TOBACCO` | Carved out of the Rule 26(a) exemption |
| `DRUG_FORMULATION` | Rule 26(c) — outside these rules |
| `MEDICAL_DEVICE` | Proviso to Rule 26(c) — back in scope |
| `RESTAURANT_FAST_FOOD` | Rule 26(b) |
| `HANDLOOM_THREAD_COIL` | Rule 26(e) |

Category MUST be set by the officer at capture, defaulting to `GENERIC`. It MUST NOT be
inferred silently; an inference MAY be offered as a suggestion the officer confirms.

### 4.7 Result

```python
@dataclass
class Result:
    check: str            # e.g. LMPC-R7-2-MIN-HEIGHT
    clause: str           # e.g. "Rule 7(2) Table-I"
    verdict: Verdict
    reason: str           # templated; no free generation
    citation: dict        # {gsr, page, dated}
    evidence: dict        # measured values, thresholds, boxes
```

**Invariant.** `citation` and `reason` MUST be non-empty on every Result, including
`NOT_APPLICABLE` and `SYSTEM_ERROR`.

### 4.8 EvaluationRun

```python
@dataclass
class EvaluationRun:
    scan_id: UUID
    results: list[Result]
    overall: str                 # Part 10.7
    counts: dict[str, int]
    gates_fired: list[str]
    fields: dict[str, str | None]
    rulepack: dict               # {version, sha256, current_to}
    disclosures: list[str]       # chain-gap disclosures — printed on every report
    manifest: dict               # Part 11.2
```

---

## Part 5 — Law compiler subsystem

Module `lmpc.lawc`. Runs offline on a build host. **MUST NOT** be importable from the
request path; CI enforces this with an import-graph check.

```
fetch → classify → extract text → identify → chain → families → parse operations
      → extract tables → cross-check against reviewer → bind → hash → publish
```

### 5.1 Source registry

| Column | Type | Notes |
|---|---|---|
| `url` | text | `http://` MUST be rewritten to `https://`; port 80 does not answer |
| `family` | text | `PACKAGED_COMMODITIES` \| `GENERAL` \| `GATC` |
| `fetched_at` | timestamptz | Every attempt recorded |
| `http_status` | int | |
| `sha256` | char(64) | Of the retrieved bytes |
| `bytes` | int | |

**Fetch contract.**
- TLS verification is disabled for `consumeraffairs.gov.in` — the certificate is expired.
  This MUST be an explicit, commented exception scoped to that host, never a global flag.
- Timeout 90 s; 4 retries; backoff `0.4·i` before attempt `i` and `1.5·(i+1)` after failure.
- A response whose body begins `<!doctype` where JSON was expected counts as a failure.
- **A failed page is skipped, never fatal.** Partial data is useful; a lost harvest is not.
- The fetcher MUST respect a 1.2 s inter-request delay on public APIs.

### 5.2 Classification

```python
pages = pdfinfo(path)              # 0 if unreadable
text  = pdftotext("-layout")       # None on non-zero exit, timeout, or OSError

if   text is None:            kind = "CORRUPT_UNREADABLE"
elif len(text) < 200 * pages: kind = "SCANNED_NEEDS_OCR"
else:                         kind = "DIGITAL"
```

`CORRUPT_UNREADABLE` and `SCANNED_NEEDS_OCR` documents MUST be recorded and **excluded
from the chain**, never half-parsed: a partially recovered gazette is worse than a missing
one.

*Measured: 22 of 30 Packaged Commodities instruments are digital; all 8 scans are 2011–2015.
18 of 18 General Rules / GATC instruments are digital.*

### 5.3 Language split

Notifications print Hindi then English. Keep a line when Devanagari characters are
**≤ 15 %** of its alphabetic characters.

```python
DEV = re.compile(r"[ऀ-ॿ]")
keep = len(DEV.findall(line)) / max(1, len([c for c in line if c.isalpha()])) <= 0.15
```

### 5.4 Instrument identity (P2)

```python
GSR       = r"G\.S\.R[.\s]*(?:number[.\s]*)?\d+\s*\(\s*E\s*\)"
DATE      = r"(\d{1,2}\s*(?:st|nd|rd|th)?\s+[A-Z][a-z]+,?\s+\d{4})"
SELF_RE   = rf"{GSR_CAP}\s*[.—–:\-]"
SELF_DATE = rf"New\s+Delhi,?\s+the\s+{DATE}"

key = f"{gsr}@{year}"          # "G.S.R. 875(E)@2016"
```

Real source defects the patterns MUST absorb, all observed in the live corpus:

| Observed | Cause |
|---|---|
| `G.S.R. . 778(E)` | Typo in the gazette itself |
| `30 th August, 2023` | `pdftotext` splits the ordinal |
| `2022were published` | Missing space in the source |
| `A < 50` where the page shows `A ≤ 50` | Embedded font lacks the `≤` glyph |

**Collision detection MUST run on every build.** Any G.S.R. number resolving to more than
one `key` is reported in `gsr_number_collisions` and logged at WARN.

### 5.5 Lineage and the chain

```python
NOTE_RE = (rf"(?P<parent>principal rules|.{{0,90}}?Rules,\s*\d{{4}}).{{0,40}}?were?\s+published"
           rf".{{0,220}}?(?P<bg>{GSR}).{{0,40}}?dated\s+(?:the\s+)?(?P<bd>{DATE})"
           rf"(?:.{{0,220}}?last\s+amended[,\s]*(?:vide)?[,\s]*(?:notification)?[,\s]*"
           rf"(?:number)?.{{0,60}}?(?P<pg>{GSR}).{{0,40}}?dated\s+(?:the\s+)?(?P<pd>{DATE}))?")
```

The `last amended` group is **optional**: the first amendment to an instrument has no
predecessor (`is_first_amendment_of_parent`).

**The chain walk is a reachability proof.** Begin at the instrument nothing points back to;
follow `prev_key` to the base rules. A pointer to a key not held is a **named missing
document**, never a silent skip.

*Measured: 12 links for Packaged Commodities (G.S.R. 418(E) 29 May 2026 → G.S.R. 60(E)
27 Jan 2023); 13 for General Rules; 4 for GATC.*

### 5.6 Family resolution — transitive

An instrument may amend the principal rules, or amend an earlier amendment of them. Both
belong to one family and the chain runs through both.

```python
def root_family(doc, by_gsr):
    cur, seen = doc["base_gsr"], set()
    while cur and cur not in seen:
        seen.add(cur)
        parent = by_gsr.get(cur)
        nxt = parent["base_gsr"] if parent else None
        if not nxt or nxt == cur:
            return cur
        cur = nxt
```

Grouping on the *declared* parent splits one chain into fragments and reports gaps that are
not gaps. *Measured: General Rules went from 4 reconstructed links to 13.*

### 5.7 Amendment operation grammar

| Phrase | Operation |
|---|---|
| `for X, the following … shall be substituted` | `substitute` |
| `after X, the following … shall be inserted` | `insert` |
| `X shall be omitted` | `omit` |
| `X shall be numbered / renumbered` | `renumber` |
| `for the words …, the words … shall be substituted` | `substitute_words` |

Each resolves to a **stable node address**:

```
lmpc/r7/sr2          rule 7, sub-rule (2)
lmpc/r7/table-I      rule 7, Table-I
lmpc/r6/sr1/cle      rule 6, sub-rule (1), clause (e)
```

*Measured: 56 operations across 30 Packaged Commodities instruments; 30 across 18
General/GATC instruments. Roughly one third currently resolve to `lmpc/?` — see Part 25.1.*

### 5.8 Table extraction

```python
ROW = (r"^\s*(\d)\s+(?P<cond>[0-9]+\s*[<≤>=]+\s*A|A\s*[<≤>=]+\s*[0-9]+|"
       r"[0-9]+\s*[<≤>=]+\s*A\s*[<≤>=]+\s*[0-9]+)\s+(?P<h>\d+\.\d)\s+(?P<m>\d+\.\d)\s*$")
```

The table is printed twice (Hindi and English renditions); de-duplicate on
`(band, min, molded)`.

Every row MUST carry `needs_human_confirmation = ("≤" not in band)`. The production
approval screen MUST crop the table region from the **page image** and display it beside
the parsed values (Part 16.7).

### 5.9 Gap register — `lawc/gaps.yaml`

```yaml
gaps:
  - gsr: "G.S.R. 910(E)"
    dated: "2022-12-29"
    referenced_by: "G.S.R. 60(E)"
    searched:
      - {source: "consumeraffairs.gov.in/pages/legal-metrology-act",
         on: "2026-09-07", result: NOT_LISTED}
      - {source: "93 PDF links enumerated from that page",
         on: "2026-09-07", result: NOT_PRESENT}
    assessment: >
      Lies on the compliance-deadline branch; no binding depends on a node it touches.
    affects_nodes: []          # non-empty intersection with bound nodes FAILS the build
    decision: ACCEPT_WITH_DISCLOSURE
    reviewer: "akshaj.tiwari"
    reviewed_on: "2026-09-07"
    disclosure: >
      One instrument in the amendment chain is not published on the DoCA website …
```

The disclosure travels inside the rulepack and prints on **every report**. This is
deliberately noisy: an unrecorded gap fails the build; a recorded one is visible forever.

*G.S.R. 910(E) of 29 Dec 2022 is genuinely absent from all 93 PDF links on the government
page. The compiler found this by reachability, not by anyone noticing.*

### 5.10 Bindings — `lawc/bindings.yaml`

The one-time human work: point each requirement at a generic operator and record what a
reviewer confirmed.

```yaml
- check: LMPC-R7-2-MIN-HEIGHT
  node: lmpc/r7/table-I            # bindings attach to the NODE, not to values
  clause: "Rule 7(2) Table-I"
  operator: table_lookup
  effective_from: 2011-04-01       # when the REQUIREMENT began
  table_effective_from: 2018-01-01 # when THIS table came into force
  citation: {gsr: "G.S.R. 629(E)", page: 11, dated: "2017-06-23"}
  params: {input: pdp_area_cm2, compare: glyph_height_mm}
  boundary_review: {status: UNRESOLVED, policy: guard_band, guard_band_cm2: 0.5}
  superseded:                      # P7 — repealed law retained
    - effective_from: 2011-04-01
      effective_to: 2017-12-31
      keyed_by: net_quantity_g
      rows: [{upper: 200, min_mm: 1.0, molded_mm: 1.0}, …]
  confirmed_values:                # build FAILS if the gazette disagrees
    - {upper_cm2: 50, min_mm: 1.0, molded_mm: 1.5}
    …
```

**Why the node address matters.** When an amendment substitutes a node's contents, the
address is unchanged, so the binding is untouched and the new values load. Ten thresholds
update with zero human editing. A binding needs revisiting only when a genuinely new *kind*
of rule appears — roughly once or twice a year.

### 5.11 Build refusal matrix

The build MUST produce **no rulepack at all** in every case below. Each has a test.

| # | Condition | Message fragment | Test |
|---|---|---|---|
| 1 | Chain hole not in `gaps.yaml` | *cannot be proven current* | `test_build_refuses_an_unacknowledged_chain_hole` |
| 2 | Acknowledged gap with no named reviewer | *named reviewer* | `test_build_refuses_a_gap_with_no_named_reviewer` |
| 3 | Gap whose `affects_nodes` intersects a bound node | *cannot stand in for the document* | `test_build_refuses_a_disclosure_that_covers_a_bound_node` |
| 4 | Gazette table values ≠ `confirmed_values` | *a human must re-review* | `test_build_refuses_when_the_gazette_disagrees_with_the_reviewer` |
| 5 | Gazette row count ≠ confirmed row count | *rows* | `test_build_refuses_on_a_row_count_change` |
| 6 | A binding names an unimplemented operator | *unimplemented operators* | build-time assertion |
| 7 | No corpus amendment substitutes a bound table node | *no amendment … substitutes* | build-time assertion |
| 8 | Empty corpus | fetch failure propagates | `test_empty_corpus_fails_loudly` |

**Warnings** (build proceeds; recorded in the pack and printed): unreadable files;
`unverified_bindings` — bindings not traceable to a corpus amendment (currently 12, all
tracing to the base 2011 rules; Part 25.2).

### 5.12 Regulatory watch service

| Property | Value |
|---|---|
| Schedule | Daily 02:00 IST |
| Action | Re-fetch each family index; diff the link inventory |
| On new link | Download, classify, parse, write `amendment_ledger` rows with `status='QUARANTINED'` |
| Notification | Email + console badge to users holding `rules:approve` |
| **Never** | Auto-promote to `ACTIVE`. Publication requires human approval (UC-5) |

A chain break discovered by the watcher MUST raise a **P2 alert** — it means the government
published something we cannot reach.

---

## Part 6 — Rulepack format and lifecycle

### 6.1 Artefact

```
rulepack/current.json     21 checks · 4 gates · ~14 KB · sha256-addressed
```

Generated, never hand-edited. It is the **only** thing the running system knows about the
law.

### 6.2 Document schema

```jsonc
{
  "rulepack": "lmpc",
  "schema": 1,
  "version": "lmpc-2026-09-07-4c38a851",       // date + first 8 of sha256
  "sha256": "4c38a851…",                        // over all but sha256/version/built_at
  "built_at": "2026-09-07T11:42:03Z",           // assigned AFTER hashing (6.5)

  "currency": {
    "newest_instrument": "G.S.R. 418(E)",
    "chain_links_verified": 12,
    "chain_complete": false,
    "corpus_documents": 30,
    "documents_needing_ocr": 8,
    "unreadable_documents": [],
    "acknowledged_gaps": [
      { "gsr": "G.S.R. 910(E)", "dated": "2022-12-29",
        "reviewer": "akshaj.tiwari", "reviewed_on": "2026-09-07",
        "affects_nodes": [], "text": "…" }
    ],
    "chain": [ { "gsr": "…", "prev": "…", "prev_date": "…" } ]
  },

  "gates":  [ /* 4 — Part 23.1 */ ],
  "checks": [ /* 21 — Part 23.2 */ ],
  "modes":  { "PHYSICAL_PACKAGE": { "excludes": [] },
              "ECOMMERCE_LISTING": { "excludes": [ … 5 … ],
                                     "citation": { "gsr": "G.S.R. 629(E)", "page": 10 } } },
  "unverified_bindings": [ "lmpc/r3", "lmpc/r8", … ]
}
```

### 6.3 Check object

```jsonc
{
  "check": "LMPC-R7-2-MIN-HEIGHT",
  "node": "lmpc/r7/table-I",
  "clause": "Rule 7(2) Table-I",
  "operator": "table_lookup",
  "field": null,                                  // for field-scoped operators
  "effective_from": "2011-04-01",
  "effective_to": null,
  "citation": { "gsr": "G.S.R. 629(E)", "page": 11, "dated": "2017-06-23" },
  "verdict_ceiling": "INDETERMINATE_NEAR_BOUNDARY",
  "only_when": { "is_imported": true },           // optional gating condition
  "not_required_when": { "scan_mode": "ECOMMERCE_LISTING" },
  "boundary_review": { "status": "UNRESOLVED", "policy": "guard_band",
                       "guard_band_cm2": 0.5 },
  "params": {
    "input": "pdp_area_cm2",
    "compare": "glyph_height_mm",
    "source_instrument": "G.S.R. 629(E)",
    "rows": [ { "upper_cm2": 50, "min_mm": 1.0, "molded_mm": 1.5,
                "band_as_printed": "A < 50",
                "boundary_operator_from_text_layer": ["<"],
                "boundary_confirmed_by_human": false } ],
    "versions": [
      { "effective_from": "2011-04-01", "effective_to": "2017-12-31",
        "keyed_by": "net_quantity_g", "source_instrument": "G.S.R. 202(E)",
        "rows": [ { "upper": 200, "min_mm": 1.0, "molded_mm": 1.0 } ] },
      { "effective_from": "2018-01-01", "effective_to": null,
        "keyed_by": "pdp_area_cm2", "source_instrument": "G.S.R. 629(E)",
        "rows": [ … ] }
    ]
  }
}
```

### 6.4 Gate object

```jsonc
{
  "id": "GATE-R26-EXEMPT",
  "clause": "Rule 26",
  "node": "lmpc/r26",
  "operator": "applicability",
  "citation": { "gsr": "G.S.R. 202(E)", "page": 17, "dated": "2011-03-07" },
  "params": { "any_of": [
      { "field": "net_quantity_g", "lte": 10,
        "unless_field": "category", "unless_in": ["TOBACCO"] },
      { "field": "category", "in": ["RESTAURANT_FAST_FOOD"] } ] },
  "effect": "ALL_RULES_NOT_APPLICABLE",
  "exceptions": []                                 // for SKIP_TYPOGRAPHY_EXCEPT
}
```

**Condition grammar.** A condition is an object with `field` plus one of `in`, `eq`, `gt`,
`lte`; optionally `unless_field` + `unless_in`, and optionally `and_field` + `gt`. A
condition with none of `in|eq|gt|lte` MUST evaluate false — an empty condition MUST NOT
match everything.

**Effects.** `CHAPTER_II_NOT_APPLICABLE` · `ALL_RULES_NOT_APPLICABLE` ·
`SKIP_TYPOGRAPHY_EXCEPT` (with `exceptions[]`).

### 6.5 Integrity and reproducibility

```python
def digest(pack) -> str:
    body = {k: v for k, v in pack.items() if k not in ("sha256", "version", "built_at")}
    return sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
```

- `built_at` is assigned **after** hashing. The same corpus MUST hash identically on any
  machine at any time.
- `load()` MUST recompute the digest and raise on mismatch. Every verdict cites this hash;
  a silent edit would forge the legal basis of past findings.
- Tested: two builds of one corpus produce one hash; a weakened threshold is refused at
  load.

### 6.6 Publication lifecycle

```
DRAFT ──build──▶ CANDIDATE ──legal approval──▶ ACTIVE ──superseded──▶ ARCHIVED
```

| State | Meaning | Who moves it |
|---|---|---|
| `CANDIDATE` | Built and self-consistent, not yet approved | Build pipeline |
| `ACTIVE` | In use for new scans | `ADMIN` + `legal_reviewer` |
| `ARCHIVED` | Superseded; retained forever for reproduction | System |

- At most one `ACTIVE` rulepack per deployment.
- Publishing a new rulepack MUST NOT alter any existing `rule_evaluations` row or any
  finalised report.
- Every `scans` row records `rulepack_version` and `rulepack_sha256` at evaluation time.
- Re-evaluation (`POST /scans/{id}/reevaluate`) creates a **new** batch and leaves the old
  one intact.

### 6.7 Honesty markers

The pack MUST NOT present more certainty than it has.

| Marker | Meaning |
|---|---|
| `boundary_confirmed_by_human: false` | The `≤` glyph was lost by text extraction; anything within the guard band abstains |
| `verdict_ceiling: "INDETERMINATE"` | The check may measure and explain but never accuse |
| `verdict_ceiling: "INDETERMINATE_NEAR_BOUNDARY"` | Enforced inside `table_lookup` only |
| `acknowledged_gaps` | A notification we could not obtain, with the search performed |
| `unverified_bindings` | Bindings traced to text not present in the corpus |

---

## Part 7 — Capture subsystem

The single highest-value component: without an asserted coverage flag the engine cannot
report any violation (P4).

### 7.1 Capture state machine

```
IDLE ─▶ CATEGORY ─▶ FRONT ─▶ BACK ─▶ SIDE_1 ─▶ SIDE_2 ─▶ SCALE_REF ─▶ REVIEW ─▶ SUBMIT
                      ▲        ▲        ▲         ▲          ▲
                      └────────┴────────┴─────────┴──────────┘
                          each accepts a frame only after 7.2 passes
```

| State | Required? | Waivable? | On waive |
|---|---|---|---|
| `CATEGORY` | Yes | No | — |
| `FRONT` | Yes | No | — |
| `BACK` | Yes | Yes, with reason | `coverage_asserted = false` |
| `SIDE_1`, `SIDE_2` | No | Yes | Recorded; does not block assertion |
| `SCALE_REF` | No | Yes | `px_per_mm = null` ⇒ millimetre checks abstain |
| `REVIEW` | Yes | No | — |

### 7.2 Frame quality gates (on device, before acceptance)

| Gate | Method | Reject when | Message |
|---|---|---|---|
| Blur | variance of Laplacian on the green channel | `< 100` | "Too blurry — hold still" |
| Glare | fraction of pixels with luma `> 250` | `> 3 %` | "Glare — tilt away from the light" |
| Exposure | mean luma | `< 40` or `> 215` | "Too dark" / "Too bright" |
| Perspective | corner angles of the detected package quad | any deviation `> 20°` | "Hold the camera square to the pack" |
| Resolution | long edge | `< 1200 px` | "Move closer" |
| Coverage | detected quad area / frame area | `< 25 %` | "Fill more of the frame" |

Rejection MUST be immediate and name the problem. Diagnosing a bad photo after upload
wastes the officer's trip.

### 7.3 The coverage assertion (P4)

```typescript
scan.coverage_asserted =
    REQUIRED_PANELS.every(p => state[p].completed) &&
    REQUIRED_PANELS.every(p => !state[p].waived);
```

- MUST be computed by the client and re-validated server-side against
  `scan_images.panel_label`.
- The server MUST reject `coverage_asserted=true` if the required panels are not all
  present (`E_COVERAGE_MISMATCH`).
- Third-party or bulk-imported images MUST always carry `false`.

### 7.4 Scale reference

| Type | Source of truth | Accuracy | Availability |
|---|---|---|---|
| `ISO_ID1_CARD` | long edge = 85.60 mm | ±0.2 mm `[ESTIMATE]` | Any bank card — free |
| `APRILTAG_36H11` | printed marker, known side | ±0.1 mm `[ESTIMATE]` | Needs a printed card |
| `MANUAL_DIMENSIONS` | officer enters L×W×H in cm | secondary evidence only | Always |
| `NONE` | — | — | Millimetre checks return `INDETERMINATE` |

The marker MUST be **coplanar with the measured panel**. A non-coplanar marker MUST cause
abstention, not a corrected estimate.

### 7.5 Upload

- Images are compressed client-side to `MAX_EDGE_UPLOAD = 2400` (long edge), JPEG q=85.
- Metadata is submitted first; images follow as separate resumable parts, so one large
  photo does not block the batch.
- EXIF GPS is stripped unless the officer consented to geotagging.
- Each image carries a client-computed SHA-256; the server verifies it.

---

## Part 8 — Vision and OCR subsystem

Module `lmpc.engine.ocr`.

### 8.1 Engine

PP-OCR detection + angle classification + recognition, executed under ONNX Runtime via
`rapidocr-onnxruntime`.

```python
# Probing the provider LIST is not the same as using it: onnxruntime-gpu lists
# CUDAExecutionProvider even with no CUDA runtime present, and silently falls back.
# MUST build a probe session and ask what it actually got (M.18).
sess = ort.InferenceSession(tiny_model, providers=["CUDAExecutionProvider"])
CUDA = "CUDAExecutionProvider" in sess.get_providers()
```

Measured on this host: providers advertised `['Tensorrt','CUDA','CPU']`; a session
actually reported `['CPUExecutionProvider']` because `libcublasLt.so.13` was absent.
Every timing in this document is therefore a **CPU** figure.

Model files MUST be pinned by SHA-256 in the execution manifest (Part 11.2).

**Recognition models — the current default is wrong for this domain.**

| Model | Size | Classes | Devanagari | Latin |
|---|---|---|---|---|
| `ch_PP-OCRv3_rec` *(current default)* | 10.7 MB | 6,625 | **0** | yes |
| `en_PP-OCRv3_rec` | 9.0 MB | 95 | 0 | yes |
| `devanagari_PP-OCRv3_rec` | 9.0 MB | 167 | **86** | yes (52) |

The shipped default is the **Chinese** recogniser. It cannot emit a single Devanagari
character, so Hindi extraction is not merely untested — it is impossible (M.19). Measured
on a Hindi label rendered with Noto Sans Devanagari:

```
current (Chinese)     '3  45.00'      ' HT 500 '     'MRP Rs. 45.00 (incl. of all taxes)'  0.91
devanagari model      'अिधकतमखुदरामूलय४.॰ठरपये'  'शुदमाऋड००याम'  'MRP Rs. 45.O0 Jincl. Of all taxes'   0.90
```

The Devanagari model reads Hindi (imperfectly — matra ordering and spacing need work) and
is **slightly worse on English**. The system MUST therefore run **two specialist
recognisers** and select per region, not one general model:

| Configuration | Total model size | Hindi | English |
|---|---|---|---|
| Current: one Chinese model | 13.7 MB | none | good |
| **Required: `en` + `devanagari` + shared detector/classifier** | **~21 MB** | usable | good |

+7 MB in a server-side container is not a size concern; the models are already the
smallest class PP-OCR publishes. **Selection rule:** run both recognisers on each region
and keep the higher-confidence result, subject to a script-consistency check. `[ESTIMATE]`
— the selection policy MUST be measured against a labelled Hindi set before it ships
(Part 25.5).

### 8.2 Resolution budget

Real phone photographs in the validation corpus reach **9248 × 6936 (64 MP)**. Handing one
to the recogniser exhausts memory and never returns (M.14).

```python
MAX_EDGE = 1800
im = Image.open(path)
im.draft("RGB", (MAX_EDGE, MAX_EDGE))     # JPEG decoder downscales while decoding
im = im.convert("RGB")
if max(im.size) > MAX_EDGE:
    im = im.resize(scaled, Image.LANCZOS)  # land exactly on the cap
```

Measured, 10 products, **CPU** (M.18):

| Long edge | s / photo | Regions | MRPs found |
|---|---|---|---|
| 800 | 0.8 | 452 | 1 / 10 |
| 1280 | 0.9 | 514 | 1 / 10 |
| **1800** | **1.6** | **528** | **2 / 10** |
| 2400 | 2.3 | 558 | **3 / 10** |

Accuracy rises with resolution at roughly proportional cost, with no sweet spot. **Default
1800.** A deployment MAY raise it to 2400 where the latency budget allows; the value used
MUST be recorded per image in `scan_images.max_edge_used`.

### 8.3 Token construction

```python
for box, text, score in result:
    score = float(score)                  # RapidOCR returns confidence as a STRING
    x, y = int(min(xs)), int(min(ys))
    w, h = int(max(xs) - x), int(max(ys) - y)
    Token(text.strip(), x, y, w, h, score, panel, cap_height_px=h * CAP_RATIO)
```

`CAP_RATIO = 0.62`. **This is a documented bias, not a measurement.** Geometry is expressed
in the resized frame; every check that consumes it is a ratio, so a uniform scale cancels.

### 8.4 Glyph segmentation — the known gap (P6)

Rule 7(3) requires per-letter width and height. Detection boxes cannot supply them. Until a
segmentation pass exists, `Scan.glyph_segmentation = False` and `ratio_min` abstains.

*Before this gate existed the check produced 11 false accusations at plausible values such
as 0.151.*

Acceptance for the future implementation: mean absolute error of measured glyph height
≤ 0.15 mm against a printed calibration sheet over 20 samples.

### 8.5 Failure handling

| Condition | Behaviour |
|---|---|
| Image unreadable | `scan_images.upload_status='FAILED'`; scan continues with remaining panels; coverage assertion revoked |
| OCR returns zero regions | Not an error; downstream presence checks return `INDETERMINATE` |
| Worker OOM | Job retried once at `MAX_EDGE=1280`; second failure → `SYSTEM_ERROR` result, alert |
| GPU requested but unusable | Fall back to CPU, log at **WARN** (not ERROR — CPU is a supported configuration), emit `ocr_gpu_unavailable`. MUST verify by probing a real session, never the advertised provider list (M.18) |

---

## Part 9 — Extraction subsystem

Modules `lmpc.engine.{layout,lexicon,extract,normalize}`. **No language model** (P8).

Five jobs a language model would conventionally absorb, each handled deterministically:

| Job | Mechanism | Library |
|---|---|---|
| Identify which text is the MRP | lexicon + scored rubric | `rapidfuzz` |
| Read a mangled heading | normalised edit distance ≥ 85 | `rapidfuzz` |
| Phrase a finding | templated strings, English + Hindi | `str.format` |
| "Which documents affect Rule 6?" | SQL over `amendment_ledger` | PostgreSQL FTS |
| Propose amendment operations | gazette grammar parser (5.7) | `re` |

### 9.1 Layout assembly — mandatory

Real OCR splits an anchor from its value (`"NET WEIGHT :"` here, `"220"` three centimetres
right) and collapses spaces inside others (`"MRPRS.10/-(INCL.OFALLTAXES)"`). **An extractor
that assumes one region per declaration finds 0 MRPs in 60 real products** (M.15 series).

```python
def same_line(a, b):
    return (a.panel == b.panel and
            min(a.y+a.h, b.y+b.h) - max(a.y, b.y) > 0.45 * min(a.h, b.h))

MAX_GAP_RATIO = 6.0      # in line heights; beyond this a far column is a different statement
```

**Candidate set per scan** — all four forms, because scoring picks between them:

| # | Candidate | `repaired` |
|---|---|---|
| 1 | Every raw region | `False` |
| 2 | Every assembled line (left→right) | `False` |
| 3 | Every assembled line **respaced** | **`True`** |
| 4 | Every line joined with the line below when `gap ≤ 1.2 × line height` | **`True`** |

Producing more candidates cannot fabricate a declaration: a candidate is still recognised
text with real geometry.

```python
SPACE_REPAIR = [(r"(?<=[A-Za-z])(?=\d)", " "),   # MRPRS10 → MRPRS 10
                (r"(?<=\d)(?=[A-Za-z])", " "),
                (r"(?<=[a-z])(?=[A-Z])",  " ")]  # NutritionalInformation → Nutritional Information
```

Composite tokens carry the union of their parts' `src`, and `cap_height_px` = median of
parts.

### 9.2 Lexicon

Curated synonyms per field, English and Devanagari. Matching is `rapidfuzz.partial_ratio` —
the question is whether the line *contains* a recognisable spelling, not whether it equals
one. Needles shorter than 3 characters are skipped. **Acceptance threshold 85.**

```python
LEXICON["mrp"] = ["MRP", "M.R.P", "M.R.P.", "MAX RETAIL PRICE", "MAXIMUM RETAIL PRICE",
                  "MAX. RETAIL PRICE", "RETAIL PRICE", "एम.आर.पी", "अधिकतम खुदरा मूल्य"]
```

Normalisation before comparison strips everything outside `[A-Z0-9ऀ-ॿ]` and upper-cases.

Adding a synonym is a one-line change and MUST be accompanied by a fixture in
`tests/test_engine.py`.

### 9.3 Scoring rubric — full weights

```
anchor            = 40 · sim/100          if sim ≥ 85
                  = 12 · sim/100          otherwise
value_pattern     = +25                   field-specific parse succeeds
cotext_taxes      = +20                   "incl. of all taxes" present (mrp only)
on_pdp            = +8                    token is on the FRONT panel
not_a_price       = −18                   a price on a net-quantity candidate
negative_context  = −30                   ingredients|nutrition|allergen|recipe|storage|
                                          directions|best before|serving
low_ocr_conf      = −25 · (1 − conf)      when conf < 0.80
```

Field-specific `value_pattern` predicates:

| Field | Predicate |
|---|---|
| `mrp` | `normalize.money(text, require_currency = not anchored)` |
| `net_quantity` | `normalize.quantity(text)` |
| `mfg_date` | `normalize.month_year(text)` |
| `consumer_care` | phone `\+?\d[\d\s-]{8,}` or email `\S+@\S+\.\S+` |
| `manufacturer_block` | six-digit PIN `\b\d{6}\b` |
| `country_of_origin` | `(?i)\b(made in\|country of origin)\b` |
| `unit_sale_price` | `(?i)per\s+(g\|kg\|ml\|l\|litre\|cm\|m\|number)\b` |

`require_currency` is relaxed once the MRP anchor matched: real labels print `MRP: 10.00`
with no "Rs.", and recognisers turn `Rs` into `R` or `R5`.

**All weights MUST be persisted per extraction** in `extracted_declarations.feature_weights`
and rendered in the console (Part 16.5). "Why did you think that was the MRP?" must have a
numeric answer.

### 9.4 Provenance-aware margin

```python
FLOOR     = 45.0    # below this, nothing was really found
MARGIN    = 12.0    # closer than this, two candidates are indistinguishable
NEAR_MISS = 28.0    # above this, SOMETHING resembling the field was on the label

second = first candidate in rank order whose `src` is DISJOINT from the winner's
```

The runner-up MUST be **materially different**. A line and its respaced rewriting describe
the same pixels; treating them as rivals makes every field ambiguous and abstains on
everything.

Below `FLOOR` or below `MARGIN` the field is `None`, and diagnostics
(`top`, `margin`, `best_text`, `conf`) are retained so `presence()` can distinguish
*missing* from *unreadable* from *ambiguous*.

### 9.5 Normalisation

| Field | Output | Notes |
|---|---|---|
| `mrp` | `{amount, currency}` | Digit-confusion tolerance inside the numeral only |
| `net_quantity` | `{value, unit, as_printed}` | Canonicalised to `g` / `ml` / `n` |
| `mfg_date` | `{month, year}` | `MM/YYYY` or month-name + year |

Unit canonicalisation: `kg→g ×1000` · `gm,g→g` · `ml→ml` · `l,ltr,litre,liter→ml ×1000` ·
`no,n,u→n`.

Every parser is **total**: it returns `None` rather than guessing. A guessed value becomes a
legal finding.

### 9.6 OCR repair — scoped (P9)

```python
_OCR_FIX     = {O→0, o→0, l→1, I→1, S→5, B→8}   # G→6 and Z→2 REMOVED — see M.9
_NUMERIC_RUN = r"[0-9OolISB.,]{2,}"              # only runs already containing a digit
```

Global translation breaks the words the rule depends on: `Rs.` → `R5.`, `incl.` → `inc1.`.
Repair is applied **only inside numeric runs**, then separately as separator re-insertion.

| Outcome | Verdict effect |
|---|---|
| Matches raw | normal evaluation |
| Matches only after repair | `INDETERMINATE`, naming which repair |
| Never matches | `FAIL` if confidence permits, else `INDETERMINATE` |

**Repair may only downgrade a `FAIL`; it MUST NOT manufacture a `PASS`.** Repaired
candidates carry `repaired=True` and every operator that reads a *value* refuses them.

---

## Part 10 — Rule engine

Modules `lmpc.engine.{engine,operators}`.

### 10.1 Evaluation order

```
1. applicability gates          → NOT_APPLICABLE ends evaluation entirely
2. mode exclusions (Rule 6(10)) → NOT_APPLICABLE
3. temporal filter (10.3)       → NOT_APPLICABLE
4. per-check conditions         → NOT_APPLICABLE
5. operator dispatch            → PASS | FAIL | INDETERMINATE | REVIEW_REQUIRED
6. verdict ceiling (10.6)
```

Running a declaration check on an exempt package is how an automated system accuses someone
of breaking a rule that never applied to them. Gates run **first, always**.

### 10.2 Gate evaluation

```python
def _cond(c, scan):
    v = getattr(scan, c["field"], None)
    if "unless_field" in c and getattr(scan, c["unless_field"], None) in c["unless_in"]:
        return False
    if "in"  in c and v not in c["in"]:            return False
    if "eq"  in c and v != c["eq"]:                return False
    if "gt"  in c and not (v is not None and v > c["gt"]):   return False
    if "lte" in c and not (v is not None and v <= c["lte"]): return False
    if "and_field" in c:
        av = getattr(scan, c["and_field"], None)
        if not (av is not None and av > c["gt"]):  return False
    return any(k in c for k in ("in", "eq", "gt", "lte"))    # empty ⇒ False
```

A gate with `effect ∈ {ALL_RULES_NOT_APPLICABLE, CHAPTER_II_NOT_APPLICABLE}` ends
evaluation: every check returns `NOT_APPLICABLE` citing the gate. A gate with
`SKIP_TYPOGRAPHY_EXCEPT` removes the typography checks except those in `exceptions[]`.

### 10.3 Temporal selection (P7)

```python
def in_force(spec, on: str) -> bool:
    d = date.fromisoformat(on)
    fr, to = spec.get("effective_from"), spec.get("effective_to")
    return ((not fr or d >= date.fromisoformat(str(fr))) and
            (not to or d <= date.fromisoformat(str(to))))
```

Applied **independently** to checks and to table versions. Rule 7(2) has required a minimum
height since 2011; only the *table* changed in 2017. Dating the check to 2018 would wrongly
report "no such rule" for a 2015 inspection.

```
A 2.2 mm label on a 500 g pack, 215 cm² panel:
  31 Dec 2017 → PASS   (2.0 mm required, net-quantity table)
  01 Jan 2018 → FAIL   (2.5 mm required, panel-area table)
```

### 10.4 Operator contracts

Twelve implementations, six archetypes. Signature is uniform:

```python
def operator(spec: dict, scan: Scan, fields: Fields) -> Result
```

Parameters come from the rulepack; the code never moves when the law does.

**`presence(field)`**
```
field found                          → PASS
not scan.coverage_asserted           → INDETERMINATE  (P4)
required panels not all captured     → INDETERMINATE
diag[field].top ≥ NEAR_MISS          → INDETERMINATE  "resembles it, not identifiable"
any token conf < LEGIBLE             → INDETERMINATE  "absence from an unreadable image"
otherwise                            → FAIL
```

**`format_regex(field, regex, [phrase_any, phrase_present_at, phrase_absent_below])`**
```
regex matches raw text               → phrase check below, else PASS
matches only after repair            → INDETERMINATE (names the repair)
min token conf < ACCUSE (0.95)       → INDETERMINATE  (P5)
otherwise                            → FAIL

phrase similarity ≥ phrase_present_at (85)                        → PASS
phrase similarity < phrase_absent_below (60) and conf ≥ LEGIBLE    → FAIL
in between                                                        → INDETERMINATE
```
Legal *wording* is matched fuzzily; *digits* exactly. The digits are the finding.

**`numeric_predicate(field, predicate)`**
```
any token.repaired                   → INDETERMINATE  (P9 / M.17)
numeral span not consumed end to end → INDETERMINATE  (M.7: "45.b0" read as 45.0)
numeral contains confusable chars    → INDETERMINATE
conf < LEGIBLE                       → INDETERMINATE
otherwise                            → predicate(amount) ? PASS : FAIL
```
Implemented predicates: `rounded_to_rupee_or_50_paise`.

**`table_lookup(input, compare, versions)`**
```
pdp_area unknown                     → INDETERMINATE "dimensions not supplied"
scan.px_per_mm is None               → INDETERMINATE "no scale reference"
select the version in force on scan.captured_at; none → INDETERMINATE
if version.keyed_by != "pdp_area_cm2":
    use that key (e.g. net_quantity_g); key missing → INDETERMINATE
area within guard_band_cm2 of a band edge AND boundary_review UNRESOLVED
                                     → INDETERMINATE (names the boundary)
|measured − required| ≤ (1 px in mm) → INDETERMINATE "straddles the threshold"
otherwise                            → measured ≥ required ? PASS : FAIL
```
`measured` = max `cap_height_px` over tokens of the `mrp` and `net_quantity` fields,
divided by `px_per_mm`. Uncertainty = `1 / px_per_mm`.

**`ratio_min(numerator, denominator, min, exclude_glyphs)`**
```
not scan.glyph_segmentation          → INDETERMINATE  (P6 / M.15)
only MANDATORY declaration fields are measured — never marketing copy (M.15)
composite tokens (len(src) > 1) skipped
no measurable single region          → INDETERMINATE
ratio outside [0.05, 3.0]            → INDETERMINATE "detection artefact"
otherwise                            → ratio ≥ min ? PASS : FAIL
```
`MANDATORY = {mrp, net_quantity, mfg_date, consumer_care, manufacturer_block,
country_of_origin, unit_sale_price}`.

**`clear_space(field, above_below_multiple, left_right_multiple)`**
```
field not established                → NOT_APPLICABLE
composite quantity token             → INDETERMINATE
any measured distance < 0            → INDETERMINATE "regions overlap"
otherwise → both ≥ multiple × numeral height ? PASS : FAIL
```
Distances are measured to the nearest other token on the same panel that overlaps in the
perpendicular axis.

**`tiered_format(field, tiers)`** — picks the required form from net quantity, then checks
the declared unit word. Quantity unknown → `INDETERMINATE`.

**`cross_field(expr, tolerance_pct, on_mismatch)`** — unit price vs MRP ÷ quantity;
deviation beyond tolerance returns `on_mismatch` (`REVIEW_REQUIRED`).

**`script_allowed(allowed_scripts, additional_permitted)`** — Rule 9(4). A third script is
never itself a violation; only the **absence of both** permitted scripts is.

**`mrp_uniqueness(on_two_values)`** — two distinct prices → `REVIEW_REQUIRED`; a revised
lower price is lawful (Rule 6(3) proviso).

**`date_plausible(not_after, not_before, on_violation)`** — a packing date after the
inspection or before commencement → `REVIEW_REQUIRED`, never `FAIL`.

**`small_package_mark(capacity_cm3_at_or_below, relaxes)`** — Rule 10(1) proviso at
≤ 10 cm³ (raised from 5 in 2017).

**`applicability`** — gates only; see 10.2.

### 10.5 Confidence thresholds (P5)

```python
LEGIBLE   = 0.80    # below: a token supports no finding at all
ACCUSE    = 0.95    # below: no CHARACTER-LEVEL accusation
NEAR_MISS = 28.0    # rubric score above which "something like it" was present
```

*One threshold for all claims produced either false accusations or silent misses. Three
thresholds gave 0 % false accusations and 0 missed violations simultaneously.*

### 10.6 Verdict ceilings

| Ceiling | Effect | Applied where |
|---|---|---|
| `INDETERMINATE` | The check may measure and explain but never `FAIL` | Generic engine wrapper `_ceiling()` |
| `INDETERMINATE_NEAR_BOUNDARY` | Abstain only within the guard band | **Inside** `table_lookup` — never a blanket cap (M.1) |

A ceiling MUST record `ceiling_reason` in the rulepack; the engine appends it to the
verdict's `reason`.

### 10.7 Overall status

```
SYSTEM_ERROR        if any SYSTEM_ERROR
NON_COMPLIANT       elif any FAIL
REVIEW_REQUIRED     elif any REVIEW_REQUIRED
INCOMPLETE_EVIDENCE elif any INDETERMINATE
OUT_OF_SCOPE        elif every result NOT_APPLICABLE
COMPLIANT           otherwise
```

### 10.8 Error containment

Any exception raised by an operator MUST be caught and converted to a `SYSTEM_ERROR`
Result carrying the exception type and message. **An engineering defect MUST NOT surface as
a legal finding against a trader.** Tested by
`test_a_broken_operator_reports_system_error_not_a_violation`.

---

## Part 11 — Evidence, reporting, repository

### 11.1 Evidence integrity

- Original frames MUST be written to object storage **before** processing, addressed by
  SHA-256, and never mutated. Derived images (crops, overlays) are separate objects.
- Object storage MUST have versioning enabled.
- Every `Result` carries `check, clause, verdict, reason, citation, evidence`.
- Retention: originals and reports are **never hard-deleted**; see Part 13.6.

### 11.2 Execution manifest

Written per evaluation run; enables SC-6.

```json
{
  "scan_id": "…", "evaluated_at": "…",
  "rulepack": { "version": "lmpc-2026-09-07-4c38a851", "sha256": "…" },
  "law_versions": { "LMPC-R7-2-MIN-HEIGHT": "2018-01-01" },
  "models": [ { "name": "ch_PP-OCRv3_det_infer.onnx", "sha256": "…" } ],
  "params": { "MAX_EDGE": 1800, "CAP_RATIO": 0.62, "FLOOR": 45.0, "MARGIN": 12.0,
              "LEGIBLE": 0.80, "ACCUSE": 0.95 },
  "code": { "git_sha": "…", "container_digest": "sha256:…" },
  "inputs": [ { "storage_key": "…", "sha256": "…", "max_edge_used": 1800 } ]
}
```

### 11.3 Report content

Sections in order, mandatory:

1. Identification — product, brand, manufacturer, barcode, category
2. Overall status and the count of each verdict
3. Scan metadata — officer, jurisdiction, capture date, geolocation if consented
4. **Coverage statement** — which panels were photographed; whether coverage was asserted
5. Per-check table — clause · verdict · measured value · required value · citation
6. Annotated evidence crops, one per finding, with the bounding box drawn
7. Officer notes
8. Reviewer sign-off block
9. **Chain-gap disclosures** (6.2 `acknowledged_gaps`)
10. Rulepack version and SHA-256; report content hash; page `n of m`

### 11.4 Rendering

- PDF via WeasyPrint; DOCX via `docxtpl`. **Both MUST render from one verdict object** —
  never a PDF→DOCX conversion.
- Storage keys: `reports/{scan_id}/{version}/report.pdf` and `.docx`.
- The DB stores only the storage key and the content hash, never bytes.
- Re-finalising creates version `n+1`; all versions are retained.

### 11.5 Repository and deduplication

```sql
dedup_key = lower(coalesce(brand_name,'') || '|' ||
                  coalesce(manufacturer_id::text,'') || '|' ||
                  coalesce(barcode,''))
```

Barcode data from an external registry is **convenience only**: it pre-fills officer form
fields and MUST NOT enter `extracted_declarations` or reach the rule engine. If a registry
says ₹45 and the label says ₹40, the label governs.

### 11.6 Search

PostgreSQL full-text plus `pg_trgm` fuzzy matching on manufacturer and brand names, with
btree indexes on category, status, date and jurisdiction. Migration to OpenSearch is
permitted **only** when p95 search latency exceeds 2 s on production volume.

---

## Part 12 — HTTP API specification

Base path `/api/v1`. JSON unless noted. All times ISO-8601 UTC. All IDs UUIDv4.

### 12.1 Conventions

| Aspect | Rule |
|---|---|
| Auth | `Authorization: Bearer <access_token>` on every endpoint except `/auth/login`, `/auth/refresh`, `/healthz` |
| Idempotency | `Idempotency-Key` header honoured on all POST; `client_uuid` additionally on `/scans` |
| Pagination | `?page=1&page_size=25`; max 100; response envelope `{items, page, page_size, total}` |
| Sorting | `?sort=-created_at` |
| Errors | `{"error": {"code", "message", "details": []}}` — codes in Appendix A |
| Rate limit | 60 req/min per user; 429 with `Retry-After` |
| Versioning | Breaking changes ship at `/api/v2`; `/api/v1` supported 12 months |

### 12.2 Authentication

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/auth/login` | `{email, password, otp?}` | `200 {access_token, refresh_token, expires_in, user}` · `401 E_BAD_CREDENTIALS` · `403 E_MFA_REQUIRED` |
| POST | `/auth/refresh` | `{refresh_token}` | `200 {access_token, expires_in}` · `401 E_REFRESH_REVOKED` |
| POST | `/auth/logout` | `{refresh_token}` | `204` |
| GET | `/auth/me` | — | `200 {id, full_name, email, role, jurisdiction, permissions[]}` |
| POST | `/auth/mfa/enroll` | — | `200 {secret, qr_svg}` |
| POST | `/auth/mfa/verify` | `{otp}` | `204` |

### 12.3 Scans

**`POST /scans`** — `multipart/form-data`

| Part | Type | Required | Notes |
|---|---|---|---|
| `client_uuid` | uuid | Yes | Idempotency key generated on device |
| `captured_at` | date | Yes | Selects the governing law (P7) |
| `mode` | enum | Yes | `PHYSICAL_PACKAGE` \| `ECOMMERCE_LISTING` |
| `category` | enum | Yes | Part 4.6 |
| `buyer_type` | enum | No | Default `RETAIL` |
| `package_shape` | enum | No | Default `RECTANGULAR` |
| `coverage_asserted` | bool | Yes | Server re-validates (7.3) |
| `panels[]` | string[] | Yes | Panel label per image, same order as `images[]` |
| `images[]` | file[] | Yes | 1–6, JPEG/PNG/HEIC, ≤ 20 MB each |
| `image_sha256[]` | string[] | Yes | Verified server-side |
| `scale_reference` | json | No | `{type, data}` |
| `dimensions` | json | No | `{h_cm, w_cm, capacity_cm3}` |
| `flags` | json | No | `{is_imported, is_molded, other_law_requires_same_info}` |
| `geo` | json | No | `{lat, lng}` — only if consented |
| `ecommerce` | json | If mode=EC | `{url, listing_text}` |

Responses: `202 {scan_id, status, status_url}` · `400 E_VALIDATION` ·
`409 E_COVERAGE_MISMATCH` · `413 E_IMAGE_TOO_LARGE` · `415 E_UNSUPPORTED_MEDIA`.
A repeated `client_uuid` returns `200` with the existing `scan_id` — never a duplicate.

**`GET /scans/{id}`** → `200`

```jsonc
{ "id": "…", "status": "EVALUATION_COMPLETE", "overall": "NON_COMPLIANT",
  "captured_at": "2026-09-07", "coverage_asserted": true,
  "panels_captured": ["FRONT","BACK"],
  "rulepack": {"version": "…", "sha256": "…", "current_to": "G.S.R. 418(E)"},
  "disclosures": ["…"],
  "images": [{"id":"…","panel":"FRONT","url":"…","width":1800,"height":1350,
              "quality":{"blur":142,"glare":0.01}}],
  "declarations": [{"field":"mrp","text":"MRP Rs. 45.00 (incl. of all taxes)",
                    "bbox":[120,340,410,28],"confidence":0.97,
                    "score":93.0,"margin":79.0,
                    "feature_weights":{"anchor":40.0,"value_pattern":25.0,
                                       "cotext_taxes":20.0,"on_pdp":8.0}}],
  "evaluations": [{"id":"…","check":"LMPC-R7-2-MIN-HEIGHT","clause":"Rule 7(2) Table-I",
                   "verdict":"FAIL","reason":"measured 1.86 mm against a required 2.5 mm…",
                   "citation":{"gsr":"G.S.R. 629(E)","page":11},
                   "evidence":{"measured_mm":1.86,"uncertainty_mm":0.08,
                               "required_mm":2.5,"pdp_area_cm2":214.8},
                   "law_version":"2018-01-01","is_override":false}] }
```

**`GET /scans`** — filters: `manufacturer, brand, category, status, overall, date_from,
date_to, officer_id, jurisdiction_id, violation_type, q`. `403` if the requested
jurisdiction is outside the caller's scope.

**`PATCH /scans/{id}`** — body may contain `product_id`, `package_shape`, `category`,
`dimensions`. Requires `scans:update`. Mutating a `FINALIZED` scan → `409 E_SCAN_FINALIZED`.

**`POST /scans/{id}/reevaluate`** → `202`. Creates a new evaluation batch. MUST NOT modify
prior batches or any finalised report.

**`POST /scans/{id}/declarations/{field}`** — officer correction.
Body `{text, bbox?}` → `200`. Recorded as a new `extracted_declarations` row with
`corrected_by`; the original is retained.

### 12.4 Evaluations and review

| Method | Path | Notes |
|---|---|---|
| GET | `/scans/{id}/evaluations` | Latest batch by default; `?batch=n` for history |
| POST | `/scans/{id}/evaluations/{eid}/override` | `{outcome, reason}`; `reason` ≥ 10 chars; append-only |

`403 E_FORBIDDEN` unless the caller holds `evaluations:override`.

### 12.5 Reports

| Method | Path | Notes |
|---|---|---|
| POST | `/scans/{id}/report` | Finalise → `201 {report_id, version}`. `409` if unresolved `SYSTEM_ERROR` results exist |
| GET | `/reports/{id}` | Metadata including `content_sha256` |
| GET | `/reports/{id}/download?format=pdf\|docx` | `302` to a signed URL, TTL 300 s |
| GET | `/products/{id}/reports` | Full history |

### 12.6 Rulepack administration

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/rulepacks` | `rules:read` | All versions with state |
| GET | `/rulepacks/{version}` | `rules:read` | Full document |
| GET | `/rulepacks/{version}/diff/{other}` | `rules:read` | Structured diff |
| POST | `/rulepacks/{version}/approve` | `rules:approve` | `CANDIDATE → ACTIVE`; body `{confirmations:[{node, boundary_operators}]}` |
| GET | `/amendments/pending` | `rules:read` | Quarantined ledger rows |
| POST | `/amendments/{id}/approve` | `rules:approve` | |
| POST | `/amendments/{id}/reject` | `rules:approve` | `{reason}` |

Approving a rulepack MUST require explicit confirmation of every row where
`boundary_confirmed_by_human` is false; otherwise `400 E_BOUNDARY_UNCONFIRMED`.

### 12.7 Dashboard

| Method | Path | Returns |
|---|---|---|
| GET | `/dashboard/summary` | counts by period, pending reviews, violation rate |
| GET | `/dashboard/violations-by-type` | `[{check, clause, count}]` |
| GET | `/dashboard/top-non-compliant` | `[{manufacturer, count}]` |
| GET | `/dashboard/geo` | geotagged density, if consented data exists |
| GET | `/dashboard/quality` | extraction rates, abstention rates, false-accusation guard |

All dashboard queries MUST apply the caller's jurisdiction filter server-side.

### 12.8 Synchronisation

| Method | Path | Notes |
|---|---|---|
| POST | `/sync/scans/batch` | `{scans:[…]}` → `200 {results:[{client_uuid, status}]}` where status ∈ `created \| duplicate_ignored \| conflict` |
| GET | `/sync/status?since=` | Server-side changes in the caller's jurisdiction |
| POST | `/sync/images/{scan_id}` | Resumable chunk upload; `Content-Range` required |

### 12.9 Operations

| Method | Path | Auth | Returns |
|---|---|---|---|
| GET | `/healthz` | none | `200 {status:"ok"}` |
| GET | `/readyz` | none | DB, Redis, object storage, rulepack integrity |
| GET | `/version` | none | `{git_sha, rulepack_version, rulepack_sha256}` |
| GET | `/metrics` | internal | Prometheus exposition |

---

## Part 13 — Database schema and data lifecycle

PostgreSQL 16. Migrations via Alembic; every migration MUST be reversible or explicitly
marked irreversible with a reason.

### 13.1 Identity and access

```sql
CREATE TABLE jurisdictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(150) NOT NULL,
    state VARCHAR(100) NOT NULL,
    parent_jurisdiction_id UUID REFERENCES jurisdictions(id),
    path LTREE,                              -- materialised hierarchy for scope queries
    UNIQUE (name, state));
CREATE INDEX idx_jurisdiction_path ON jurisdictions USING gist (path);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(200) NOT NULL,
    email CITEXT UNIQUE NOT NULL,
    phone VARCHAR(20),
    role VARCHAR(30) NOT NULL CHECK (role IN
        ('FIELD_OFFICER','REVIEWING_OFFICER','ADMIN','AUDITOR')),
    is_legal_reviewer BOOLEAN NOT NULL DEFAULT FALSE,
    jurisdiction_id UUID REFERENCES jurisdictions(id),
    department VARCHAR(150),
    external_subject VARCHAR(255) UNIQUE,    -- OIDC 'sub' when SSO is used
    password_hash TEXT,                      -- NULL when SSO-only
    mfa_secret_enc BYTEA,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,     -- sha256; the token itself is never stored
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    user_agent TEXT, ip INET);
CREATE INDEX idx_refresh_user ON refresh_tokens(user_id) WHERE revoked_at IS NULL;
```

### 13.2 Product domain

```sql
CREATE TABLE commodity_categories (
    code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    fssai_overlap BOOLEAN NOT NULL DEFAULT FALSE,
    default_exemptions JSONB NOT NULL DEFAULT '[]');

CREATE TABLE manufacturers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    registered_address TEXT,
    external_registry_ref VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_name VARCHAR(255),
    manufacturer_id UUID REFERENCES manufacturers(id),
    category_code VARCHAR(50) NOT NULL REFERENCES commodity_categories(code),
    barcode VARCHAR(50),
    declared_net_quantity VARCHAR(50),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    dedup_key VARCHAR(500) GENERATED ALWAYS AS (lower(
        coalesce(brand_name,'') || '|' ||
        coalesce(manufacturer_id::text,'') || '|' ||
        coalesce(barcode,''))) STORED,
    UNIQUE (dedup_key));
```

### 13.3 Scans and evidence

```sql
CREATE TABLE scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_uuid UUID UNIQUE,                          -- offline idempotency
    product_id UUID REFERENCES products(id),
    officer_id UUID NOT NULL REFERENCES users(id),
    jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(id),

    captured_at DATE NOT NULL,                        -- P7 — governing law
    mode VARCHAR(20) NOT NULL CHECK (mode IN ('PHYSICAL_PACKAGE','ECOMMERCE_LISTING')),
    category_code VARCHAR(50) NOT NULL REFERENCES commodity_categories(code),
    buyer_type VARCHAR(20) NOT NULL DEFAULT 'RETAIL'
        CHECK (buyer_type IN ('RETAIL','INDUSTRIAL','INSTITUTIONAL')),
    package_shape VARCHAR(20) CHECK (package_shape IN
        ('RECTANGULAR','CYLINDRICAL','IRREGULAR')),

    coverage_asserted BOOLEAN NOT NULL DEFAULT FALSE, -- P4
    panels_captured VARCHAR(10)[] NOT NULL DEFAULT '{}',
    glyph_segmentation BOOLEAN NOT NULL DEFAULT FALSE,

    scale_reference_type VARCHAR(20) CHECK (scale_reference_type IN
        ('ISO_ID1_CARD','APRILTAG_36H11','MANUAL_DIMENSIONS','NONE')),
    scale_reference_data JSONB,
    px_per_mm NUMERIC(8,3),
    pdp_h_cm NUMERIC(7,2), pdp_w_cm NUMERIC(7,2),
    pdp_area_cm2 NUMERIC(10,2),
    capacity_cm3 NUMERIC(10,2),
    net_quantity_g NUMERIC(12,3), net_quantity_ml NUMERIC(12,3),
    is_imported BOOLEAN NOT NULL DEFAULT FALSE,
    is_molded BOOLEAN NOT NULL DEFAULT FALSE,
    other_law_requires_same_info BOOLEAN NOT NULL DEFAULT FALSE,

    ecommerce_url TEXT, ecommerce_text TEXT,
    geo_lat NUMERIC(9,6), geo_lng NUMERIC(9,6),

    rulepack_version VARCHAR(60), rulepack_sha256 CHAR(64),
    status VARCHAR(30) NOT NULL DEFAULT 'RECEIVED' CHECK (status IN
        ('RECEIVED','OCR_IN_PROGRESS','OCR_COMPLETE','EXTRACTION_COMPLETE',
         'EVALUATION_COMPLETE','UNDER_REVIEW','FINALIZED','SYNC_CONFLICT','FAILED')),
    overall VARCHAR(24),
    synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE INDEX idx_scans_jur_date  ON scans(jurisdiction_id, captured_at DESC);
CREATE INDEX idx_scans_status    ON scans(status) WHERE status <> 'FINALIZED';
CREATE INDEX idx_scans_officer   ON scans(officer_id, created_at DESC);
CREATE INDEX idx_scans_product   ON scans(product_id);

CREATE TABLE scan_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    panel_label VARCHAR(10) NOT NULL,
    storage_key TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    width_px INT, height_px INT, max_edge_used INT,
    quality JSONB,                                     -- blur, glare, exposure, skew
    upload_status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (upload_status IN ('PENDING','UPLOADING','UPLOADED','FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (scan_id, panel_label, sha256));
```

### 13.4 Extraction and evaluation

```sql
CREATE TABLE extracted_declarations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    scan_image_id UUID REFERENCES scan_images(id),
    batch INT NOT NULL DEFAULT 1,
    field_type VARCHAR(40) NOT NULL,
    raw_text TEXT,
    normalized_value JSONB,
    bbox_x INT, bbox_y INT, bbox_w INT, bbox_h INT,
    ocr_confidence NUMERIC(4,3),
    score NUMERIC(6,2), runner_up_margin NUMERIC(6,2),
    feature_weights JSONB,                    -- why this candidate won (9.3)
    source_token_ids JSONB,
    is_composite BOOLEAN NOT NULL DEFAULT FALSE,
    is_repaired BOOLEAN NOT NULL DEFAULT FALSE,        -- P9
    glyph_height_px NUMERIC(8,2), glyph_height_mm NUMERIC(6,2),
    is_on_pdp BOOLEAN,
    corrected_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX idx_extracted_scan ON extracted_declarations(scan_id, batch);

CREATE TABLE rule_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    batch INT NOT NULL DEFAULT 1,
    check_code VARCHAR(60) NOT NULL,
    clause VARCHAR(100) NOT NULL,
    outcome VARCHAR(25) NOT NULL CHECK (outcome IN
        ('PASS','FAIL','INDETERMINATE','NOT_APPLICABLE','REVIEW_REQUIRED','SYSTEM_ERROR')),
    reason TEXT NOT NULL,
    citation JSONB NOT NULL,
    evidence JSONB,
    rulepack_version VARCHAR(60) NOT NULL,
    law_version DATE,
    evidence_declaration_id UUID REFERENCES extracted_declarations(id),
    is_override BOOLEAN NOT NULL DEFAULT FALSE,
    override_of_evaluation_id UUID REFERENCES rule_evaluations(id),
    override_reason TEXT,
    overridden_by UUID REFERENCES users(id),
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (NOT is_override OR (override_reason IS NOT NULL AND overridden_by IS NOT NULL)));
CREATE INDEX idx_eval_scan  ON rule_evaluations(scan_id, batch);
CREATE INDEX idx_eval_check ON rule_evaluations(check_code, outcome);
```

**`rule_evaluations` is append-only.** `UPDATE` and `DELETE` MUST be revoked from the
application role; an override inserts a new row referencing the original.

### 13.5 Reports, rulepacks, ledger, audit

```sql
CREATE TABLE compliance_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES scans(id),
    version INT NOT NULL,
    overall_status VARCHAR(24) NOT NULL,
    pdf_storage_key TEXT, docx_storage_key TEXT,
    content_sha256 CHAR(64) NOT NULL,
    manifest JSONB NOT NULL,                      -- Part 11.2
    reviewed_by UUID REFERENCES users(id),
    review_notes TEXT,
    finalized_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (scan_id, version));

CREATE TABLE rulepacks (
    version VARCHAR(60) PRIMARY KEY,
    sha256 CHAR(64) NOT NULL UNIQUE,
    state VARCHAR(12) NOT NULL DEFAULT 'CANDIDATE'
        CHECK (state IN ('CANDIDATE','ACTIVE','ARCHIVED')),
    newest_instrument VARCHAR(40),
    chain_links INT, chain_complete BOOLEAN,
    disclosures JSONB, payload JSONB NOT NULL,
    built_at TIMESTAMPTZ, published_at TIMESTAMPTZ,
    approved_by UUID REFERENCES users(id),
    approval_confirmations JSONB);
CREATE UNIQUE INDEX one_active_rulepack ON rulepacks((state)) WHERE state = 'ACTIVE';

CREATE TABLE amendment_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_key VARCHAR(40) NOT NULL,          -- "G.S.R. 875(E)@2016"  (P2)
    family VARCHAR(40), prev_key VARCHAR(40),
    op VARCHAR(20), node VARCHAR(80), quote TEXT,
    source_file TEXT, source_sha256 CHAR(64), page INT,
    status VARCHAR(20) NOT NULL DEFAULT 'QUARANTINED'
        CHECK (status IN ('QUARANTINED','APPROVED','REJECTED')),
    approved_by UUID REFERENCES users(id), approved_at TIMESTAMPTZ,
    reject_reason TEXT);
CREATE INDEX idx_ledger_node   ON amendment_ledger(node);
CREATE INDEX idx_ledger_status ON amendment_ledger(status) WHERE status = 'QUARANTINED';

CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL, entity_id UUID,
    actor_id UUID REFERENCES users(id),
    action VARCHAR(50) NOT NULL,
    diff JSONB, ip INET, user_agent TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_time   ON audit_log(occurred_at DESC);

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE INDEX idx_manufacturers_name_trgm ON manufacturers USING gin (name gin_trgm_ops);
CREATE INDEX idx_products_brand_trgm     ON products      USING gin (brand_name gin_trgm_ops);
```

Audited actions MUST include: `LOGIN`, `LOGIN_FAILED`, `LOGOUT`, `PERMISSION_DENIED`,
`SCAN_CREATE`, `DECLARATION_CORRECT`, `EVALUATION_OVERRIDE`, `REPORT_FINALIZE`,
`RULEPACK_APPROVE`, `AMENDMENT_APPROVE`, `AMENDMENT_REJECT`, `USER_CREATE`, `ROLE_CHANGE`.

### 13.6 Data lifecycle and retention

| Data | Retention | Deletion |
|---|---|---|
| Original scan images | 7 years `[VERIFY against departmental records policy]` | Never hard-deleted while a report references them |
| Derived crops/overlays | Regenerable; 90 days | Purgeable |
| `rule_evaluations` | Permanent | Append-only; never deleted |
| `compliance_reports` | Permanent | Never deleted |
| `rulepacks` | Permanent | `ARCHIVED`, never removed — required for SC-6 |
| `audit_log` | 7 years | Partitioned monthly; older partitions moved to cold storage |
| `refresh_tokens` | 30 days after expiry | Hard-deleted |
| Geolocation | Only if consented; deletable on request | Hard-deleted on request |

Personal data held: officer identity (name, email, phone) and optional geolocation. Trader
and manufacturer details are business data. A data-subject deletion request MUST anonymise
`users` rows while preserving referential integrity — replacing name and email with
tombstones and retaining the ID.

---

## Part 14 — Authentication

### 14.1 Model

Primary: **Keycloak (OIDC)**, authorisation-code flow with PKCE for the web console,
resource-owner flow permitted only for the mobile client on departmental networks.
The application MUST NOT implement its own password hashing when SSO is available; the
local-password path exists only for deployments without an identity provider.

### 14.2 Tokens

| Token | Lifetime | Storage | Revocation |
|---|---|---|---|
| Access (JWT, RS256) | **15 min** | Memory only in the web client; never `localStorage` | Expiry only |
| Refresh (opaque, 256-bit) | **30 days**, rolling | `httpOnly; Secure; SameSite=Strict` cookie (web); encrypted secure storage (mobile) | Hashed row in `refresh_tokens`; revocable |
| ID token | 15 min | Not persisted | — |

JWT claims: `sub`, `role`, `jurisdiction_id`, `permissions[]`, `jti`, `iat`, `exp`, `aud`,
`iss`. Signature verification MUST use the IdP JWKS with a cached key set and a 10-minute
refresh.

### 14.3 Password policy (local path only)

Minimum 12 characters; checked against the top-10 000 breached-password list; Argon2id
(`m=64 MiB, t=3, p=4`). Five failed attempts within 15 minutes locks the account for
15 minutes and writes `LOGIN_FAILED` audit rows.

### 14.4 MFA

TOTP (RFC 6238), 30 s step, 6 digits, ±1 step drift.
**MANDATORY for `ADMIN` and for any user with `is_legal_reviewer`.** Optional otherwise.
Ten single-use recovery codes issued at enrolment, stored Argon2id-hashed.

### 14.5 Session rules

- Refresh rotation: every use issues a new refresh token and revokes the old one.
- Reuse of a revoked refresh token MUST revoke the entire family and raise a security alert.
- Logout revokes the presented refresh token; "log out everywhere" revokes all for the user.
- A role or jurisdiction change MUST revoke all of that user's refresh tokens.

---

## Part 15 — Authorisation and RBAC

### 15.1 Model

Role-based, with **jurisdiction scoping applied as a mandatory server-side query filter**.
Enforcement is at the API layer via a dependency that runs before the handler. UI hiding is
a convenience, never a control.

### 15.2 Permissions

```
scans:create  scans:read  scans:update  scans:reevaluate
declarations:correct
evaluations:read  evaluations:override
reports:create  reports:read  reports:export
products:read  products:merge
rules:read  rules:approve
users:read  users:manage
jurisdictions:manage
dashboard:read  dashboard:read_all
audit:read
```

### 15.3 Role → permission matrix

| Permission | FIELD_OFFICER | REVIEWING_OFFICER | ADMIN | AUDITOR |
|---|:--:|:--:|:--:|:--:|
| `scans:create` | ✅ | ✅ | ✅ | — |
| `scans:read` | own | jurisdiction | all | jurisdiction |
| `scans:update` | own, pre-review | jurisdiction | all | — |
| `scans:reevaluate` | — | ✅ | ✅ | — |
| `declarations:correct` | own, pre-review | ✅ | ✅ | — |
| `evaluations:read` | own | jurisdiction | all | jurisdiction |
| `evaluations:override` | — | ✅ | ✅ | — |
| `reports:create` | — | ✅ | ✅ | — |
| `reports:read` | own | jurisdiction | all | jurisdiction |
| `reports:export` | own | jurisdiction | all | jurisdiction |
| `products:read` | ✅ | ✅ | ✅ | ✅ |
| `products:merge` | — | ✅ | ✅ | — |
| `rules:read` | — | ✅ | ✅ | ✅ |
| `rules:approve` | — | — | ✅ + `is_legal_reviewer` | — |
| `users:read` | — | — | ✅ | ✅ |
| `users:manage` | — | — | ✅ | — |
| `jurisdictions:manage` | — | — | ✅ | — |
| `dashboard:read` | own | jurisdiction | all | jurisdiction |
| `dashboard:read_all` | — | — | ✅ | — |
| `audit:read` | — | — | ✅ | ✅ |

"own" = `scans.officer_id = current_user.id`.
"jurisdiction" = the caller's jurisdiction **and all descendants** via `jurisdictions.path`.

### 15.4 Scope enforcement

```python
def scoped(query, user, model):
    if user.has("dashboard:read_all") or user.role == "ADMIN":
        return query
    if user.role == "FIELD_OFFICER":
        return query.filter(model.officer_id == user.id)
    return query.filter(model.jurisdiction_id.in_(descendants_of(user.jurisdiction_id)))
```

- A client-supplied `jurisdiction_id` filter MAY only **narrow** the server-derived scope;
  it MUST NOT widen it.
- Every list endpoint MUST call `scoped()`. A handler that does not is a defect; CI runs a
  static check that every route reading a scoped model applies it.

### 15.5 Additional invariants

- `AUDITOR` is read-only across the entire API. Any write returns `403 E_FORBIDDEN`.
- Overriding a verdict requires a reason of at least 10 characters (`400 E_REASON_REQUIRED`).
- Finalising a report requires `reports:create` **and** that the caller is not the officer
  who captured the scan, unless the deployment sets `ALLOW_SELF_REVIEW=true`
  (single-officer offices). The setting is recorded on the report.
- Rulepack approval requires `ADMIN` **and** `is_legal_reviewer`, and MFA within the last
  15 minutes (step-up authentication).

### 15.6 Test obligation

`tests/test_rbac.py` MUST assert every cell of the matrix in 15.3 — each role attempting
each endpoint, expecting exactly `200/201/204` or `403`. A new endpoint without a matrix
row fails CI.

---

## Part 16 — Web console

Next.js 14 (App Router) · TypeScript strict · Tailwind · TanStack Query for server state ·
Zod for runtime validation of API responses. Types are generated from the OpenAPI document
and MUST NOT be hand-edited.

The console is an **enforcement workbench**, not a charts page. Officers correct
extractions, approve findings and manage rule versions here.

### 16.1 Routes

| Route | Purpose | Permission |
|---|---|---|
| `/login` | OIDC redirect or local form | — |
| `/dashboard` | Role-aware summary | `dashboard:read` |
| `/scans` | Searchable, filterable list | `scans:read` |
| `/scans/new` | Web upload path (non-guided; sets `coverage_asserted=false`) | `scans:create` |
| `/scans/[id]` | Scan detail — evidence + verdicts + corrections | `scans:read` |
| `/scans/[id]/report` | Report preview, finalise, download | `reports:read` |
| `/products/[id]` | Compliance history across scans | `products:read` |
| `/admin/rules` | Rulepack versions, diff, approval | `rules:read` |
| `/admin/amendments` | Quarantine queue | `rules:read` |
| `/admin/users` | Users, roles, jurisdictions | `users:manage` |
| `/admin/audit` | Audit log search | `audit:read` |

### 16.2 Scan detail — the primary screen

Three-pane layout at ≥ 1280 px; stacked below.

```
┌──────────────────────────────┬───────────────────────────────┐
│  IMAGE VIEWER                │  VERDICT LIST                 │
│  · panel tabs                │  · grouped by outcome         │
│  · zoom / pan                │  · FAIL first, then REVIEW,   │
│  · evidence boxes overlaid,  │    INDETERMINATE, PASS, N/A   │
│    colour-coded by outcome   │  · click ⇄ highlights the box │
│  · toggle: all / findings    │                               │
├──────────────────────────────┴───────────────────────────────┤
│  SELECTED VERDICT DETAIL                                     │
│  clause · measured · required · citation · law version       │
│  evidence crop · ScoreExplainer · [Override] [Correct field] │
└──────────────────────────────────────────────────────────────┘
```

### 16.3 Verdict presentation

Colour and iconography MUST distinguish all six states, and MUST NOT rely on colour alone
(WCAG 2.1 AA).

| Verdict | Colour token | Icon | Label |
|---|---|---|---|
| `PASS` | `--ok` green | ✓ | Compliant |
| `FAIL` | `--bad` red | ✕ | Violation |
| `INDETERMINATE` | `--unk` amber | ? | Cannot determine |
| `NOT_APPLICABLE` | `--mute` grey | – | Not applicable |
| `REVIEW_REQUIRED` | `--warn` blue | ! | Needs review |
| `SYSTEM_ERROR` | `--err` purple | ⚠ | System error |

Every card MUST show, without expansion: clause, plain-language reason, measured value,
required value. Expanding reveals: gazette citation with page, law version date, rulepack
version and hash, evidence crop, and the `ScoreExplainer`.

### 16.4 Components

| Component | Responsibility | Notes |
|---|---|---|
| `ImageAnnotationViewer` | Canvas overlay of evidence boxes | Boxes are in resized-frame coordinates; scale to display |
| `VerdictCard` / `VerdictList` | Render a `Result` | Never renders a verdict lacking a citation — renders an error instead |
| `ScoreExplainer` | Feature weights that chose a candidate | Bar per feature; shows runner-up and margin |
| `OverrideDialog` | Capture outcome + reason | Reason ≥ 10 chars; submit disabled otherwise |
| `FieldCorrector` | Edit extracted text, redraw box | Creates a new declaration row; original retained |
| `RulepackBanner` | Version, hash, `current_to`, disclosures | **Persistent on every scan and report screen** |
| `DisclosureNotice` | Chain-gap disclosures | Cannot be dismissed |
| `AmendmentDiff` | Before/after with page-image crop | Approval blocked until every unconfirmed boundary is ticked |
| `CoverageBadge` | Panels captured; asserted or not | Red when `coverage_asserted=false` |

### 16.5 The ScoreExplainer

Non-negotiable. *"Why did you think that was the MRP?"* MUST have a numeric answer on
screen:

```
MRP  ·  "MRP Rs. 45.00 (incl. of all taxes)"        score 93.0   margin 79.0
  anchor          ████████████████████  40.0   matched "MRP" at 100 %
  value_pattern   ████████████          25.0   currency + decimal numeral
  cotext_taxes    ██████████            20.0   "incl. of all taxes"
  on_pdp          ████                   8.0   front panel
  runner-up: "Net Qty: 500 g"           score 14.0
```

### 16.6 Live updates

WebSocket at `/ws/scans/{id}`, events `scan.status_changed`, `scan.evaluation_ready`.
Fallback: poll `GET /scans/{id}` every 3 s while status is in progress, backing off to 10 s
after 60 s. The client MUST stop polling on `FINALIZED` or `FAILED`.

### 16.7 Rulepack approval screen

The most safety-critical screen in the console.

- Shows a structured diff of the candidate against the active pack.
- For every row with `boundary_confirmed_by_human = false`, shows the **cropped page image**
  beside the parsed value and requires an explicit tick.
- The Approve button is disabled until every such row is ticked; the API rejects otherwise
  (`E_BOUNDARY_UNCONFIRMED`).
- Requires step-up MFA within 15 minutes.
- Displays what will *not* change: existing evaluations and finalised reports.

### 16.8 Accessibility and internationalisation

- WCAG 2.1 AA for all officer workflows: keyboard navigation, visible focus, 4.5:1 contrast,
  ARIA labels on canvas overlays with a text-equivalent verdict list.
- UI strings in `en` and `hi` via `next-intl`; **verdict reasons come from the rulepack
  templates, not the frontend catalogue**, so legal wording has exactly one source.
- Numbers, dates and currency formatted with `Intl` under the active locale; the stored
  values are never localised.

### 16.9 Performance budget

| Metric | Budget |
|---|---|
| Largest Contentful Paint, `/scans/[id]` | ≤ 2.5 s on a 4G profile |
| JS bundle, initial route | ≤ 250 KB gzipped |
| Image viewer interaction latency | ≤ 100 ms |

---

## Part 17 — Mobile client and synchronisation

A **PWA**, not a native app: any device, no store review, one codebase.
Installable, offline-capable, camera-capable via `getUserMedia`.

### 17.1 Responsibilities

The client captures, gates quality, asserts coverage, queues and uploads, and renders what
the server decided. **It holds no legal logic**: no thresholds, no comparisons, no rule
text. A rule change MUST never require a client release.

### 17.2 Local storage

| Store | Technology | Contents |
|---|---|---|
| `scans` | IndexedDB | Draft and queued scans keyed by `client_uuid` |
| `images` | IndexedDB (Blob) | Captured frames pending upload |
| `outbox` | IndexedDB | Pending mutations in order |
| `session` | Secure storage | Refresh token (encrypted), user profile |

Storage quota MUST be checked before capture; below 200 MB free the app warns and blocks
new captures until the queue drains.

### 17.3 Offline lifecycle

```
DRAFT ─▶ QUEUED ─▶ UPLOADING ─▶ SYNCED
                        └─▶ FAILED ─▶ (retry) ─▶ QUEUED
                        └─▶ CONFLICT ─▶ merge screen
```

Status MUST be visible per scan in the list.

### 17.4 Sync protocol

1. On connectivity regain, or every 5 minutes, the background sync task drains the outbox.
2. Metadata first via `POST /sync/scans/batch`, with `client_uuid` as the idempotency key.
3. Images follow via `POST /sync/images/{scan_id}` in 1 MB chunks with `Content-Range`;
   an interrupted upload resumes from the last acknowledged byte.
4. Server responds per item: `created` · `duplicate_ignored` · `conflict`.
5. Exponential backoff on failure: 5 s, 15 s, 60 s, 5 min, 30 min, then hourly.

**Conflict is possible only on shared-mutable state** — report edits and overrides, never
new scan creation. Optimistic concurrency: the client sends the version it last saw; a
mismatch returns `409` with the current server state and the client opens a merge screen.
Silent discard of either version is prohibited.

### 17.5 Camera requirements

| Requirement | Value |
|---|---|
| Capture resolution | ≥ 1920 px long edge; request `ideal: 3840` |
| Focus | Continuous autofocus; tap-to-focus |
| Torch | Toggle exposed where `MediaStreamTrack` supports it |
| Framing overlay | Panel-specific guide with the detected package quad highlighted |
| Quality gates | Part 7.2, evaluated at ≥ 5 fps on the preview stream |

Devices without `getUserMedia` fall back to the file picker, which sets
`coverage_asserted=false`.

### 17.6 Battery and thermal

Preview analysis MUST throttle to 2 fps when `navigator.getBattery()` reports < 15 % or the
device reports thermal pressure. Frames are downscaled to 2400 px before storage.

---

## Part 18 — Infrastructure, environments, configuration

### 18.1 Containers

| Image | Base | Notes |
|---|---|---|
| `lmpc/api` | `python:3.12-slim` | FastAPI + Uvicorn |
| `lmpc/worker-ocr` | `python:3.12-slim` (default) · `nvidia/cuda:12.4-runtime` (optional GPU variant) | ONNX Runtime; recogniser models baked in with pinned hashes. **The slim image is the default** — CPU meets the budget (M.18). Build the CUDA variant only where a GPU exists and higher `MAX_EDGE` or throughput is wanted |
| `lmpc/worker-rules` | `python:3.12-slim` | |
| `lmpc/worker-reports` | `python:3.12-slim` | WeasyPrint system deps |
| `lmpc/web` | `node:20-slim` → distroless | Next.js standalone output |
| `lmpc/lawc` | `python:3.12-slim` | poppler-utils for `pdftotext`/`pdfinfo` |

All base images pinned by **digest**, not tag. Images run as non-root with a read-only
root filesystem and no capabilities.

### 18.2 Environments

| Environment | Purpose | Data | Deploy |
|---|---|---|---|
| `local` | Developer laptop | Fixtures | `docker compose up` |
| `ci` | Automated tests | Ephemeral | Per pull request |
| `staging` | Pre-production | Anonymised copy | Auto on merge to `main` |
| `production` | Pilot with a real enforcement unit | Live | **Manual approval gate** |

### 18.3 Configuration

Twelve-factor: all configuration via environment variables; **no secrets in source control**.
Full list in Appendix B. Selected:

| Variable | Default | Notes |
|---|---|---|
| `LMPC_OCR_MAX_EDGE` | `1800` | Part 8.2 |
| `LMPC_OCR_DEVICE` | `auto` | `auto` \| `cuda` \| `cpu` |
| `LMPC_RULEPACK_PATH` | `/srv/rulepack/current.json` | Verified at start-up |
| `LMPC_ALLOW_SELF_REVIEW` | `false` | Part 15.5 |
| `LMPC_ACCESS_TOKEN_TTL` | `900` | seconds |
| `LMPC_REFRESH_TOKEN_TTL` | `2592000` | seconds |
| `LMPC_S3_ENDPOINT` | — | S3-compatible |
| `LMPC_DB_URL` | — | From the secrets manager |

**Start-up MUST fail fast** if the rulepack is missing, fails its integrity check, or is not
in state `ACTIVE`.

### 18.4 CI/CD

**On pull request:**
1. `ruff` + `mypy --strict` on Python; `eslint` + `tsc --noEmit` on TypeScript
2. `pytest -q` — unit, integration, adversarial
3. `python -m stress.run` — scenarios and sweeps
4. `python -m stress.campaign` — 24 validation checks
5. **P8 dependency check** — fail if any LLM package is in the runtime tree
6. **Import-graph check** — fail if `lmpc.lawc` is importable from the request path
7. **RBAC matrix completeness** — fail if a route has no matrix row
8. **Rulepack/doc consistency** (`tests/test_spec_consistency.py`) — fail if documented
   checks, gates or operators differ from the built rulepack, if a stated threshold does
   not match the code, or if a cited defect is undefined
8b. **Cross-document consistency** (`tests/test_docs_consistency.py`) — fail if any current
   document repeats a retracted claim, if defect or rule totals disagree between documents,
   if a document is missing from the index, if an internal link is broken, or if an evidence
   report whose findings were superseded carries no correction. *This exists because a
   correction once landed in the specification while four other documents went on stating
   the retracted claim.*
9. `pip-audit`, `npm audit`, Trivy image scan
10. Build images; do not push

**On merge to `main`:** integration tests against a Compose stack; push images; deploy to
staging; run the campaign against staging.

**On release tag:** manual approval, then production deploy; the rulepack version is pinned
in the release and recorded.

### 18.5 Backup and recovery

| Asset | Method | RPO | RTO |
|---|---|---|---|
| PostgreSQL | Continuous WAL archiving + nightly base backup | 5 min | 1 h |
| Object storage | Versioning + nightly replication | 24 h | 4 h |
| Rulepacks | In DB and in git | 0 | minutes |

A restore drill MUST be executed before pilot and quarterly thereafter, and its result
recorded.

### 18.6 Scaling

Workers scale on Redis queue depth: target ≤ 20 queued jobs per replica; scale up at 40,
down at 5, with a 5-minute cooldown. On the CPU image `worker-ocr` scales like any other
worker; on the CUDA variant replicas are bounded by available GPUs.
The API scales on CPU at 60 %.

---

## Part 19 — Observability and service levels

### 19.1 Logging

Structured JSON to stdout. Mandatory fields: `ts`, `level`, `service`, `trace_id`,
`scan_id`, `user_id`, `msg`. **Prohibited in logs:** access or refresh tokens, passwords,
MFA secrets, raw image bytes, full personal addresses.

### 19.2 Metrics

| Metric | Type | Purpose |
|---|---|---|
| `lmpc_scan_submitted_total` | counter | Volume |
| `lmpc_pipeline_duration_seconds{stage}` | histogram | SC-2 |
| `lmpc_ocr_regions` | histogram | Input density |
| `lmpc_ocr_gpu_unavailable_total` | counter | Fell back to CPU |
| `lmpc_verdict_total{check,outcome}` | counter | Verdict distribution |
| `lmpc_field_extracted_total{field}` | counter | SC-3 |
| **`lmpc_fail_without_coverage_total`** | **counter** | **SC-4 — MUST remain 0** |
| `lmpc_rulepack_integrity_failures_total` | counter | Tampering |
| `lmpc_chain_incomplete` | gauge | Law currency |
| `lmpc_queue_depth{queue}` | gauge | Scaling |
| `lmpc_override_total{check}` | counter | Where the engine disagrees with officers |

### 19.3 Tracing

OpenTelemetry across API → queue → workers, correlated by `scan_id` propagated as a
baggage item.

### 19.4 Service level objectives

| SLO | Target | Window |
|---|---|---|
| API availability | 99.5 % | 30 days, business hours |
| Verdict latency p95 | ≤ 15 s | 7 days |
| Verdict latency p99 | ≤ 40 s | 7 days |
| Sync success rate | ≥ 99 % within 24 h of reconnect | 30 days |
| Report generation success | ≥ 99.9 % | 30 days |

### 19.5 Alerts

| Alert | Severity | Condition |
|---|---|---|
| `FailWithoutCoverage` | **P1** | `lmpc_fail_without_coverage_total > 0` — a false-accusation defect |
| `RulepackIntegrityFailure` | **P1** | Any integrity failure |
| `ChainIncompleteUndisclosed` | **P2** | Watcher finds an unreachable instrument |
| `PipelineLatencyBreach` | P2 | p95 > 15 s for 15 min |
| `QueueBacklog` | P3 | Depth > 200 for 10 min |
| `OcrOnCpu` | P3 | `ocr_gpu_unavailable_total` increasing |

`FailWithoutCoverage` firing MUST page. It means the system is capable of accusing someone
on evidence it does not have.

### 19.6 Quality dashboard

Tracked continuously, not only at release: extraction rate per field, abstention rate per
check, override rate per check (where officers disagree), and the false-accusation guard.
A check whose override rate exceeds 20 % over 100 evaluations MUST be reviewed.

---

## Part 20 — Security

### 20.1 Threat model (STRIDE, abbreviated)

| Threat | Vector | Control |
|---|---|---|
| **Spoofing** | Stolen token | Short access TTL; rotating refresh; reuse detection revokes the family |
| **Tampering** | Edited rulepack | SHA-256 verified at load; every verdict cites the hash |
| **Tampering** | Altered evidence image | Immutable object store, versioning, hash recorded at upload |
| **Tampering** | Forged verdict history | `rule_evaluations` append-only; UPDATE/DELETE revoked |
| **Repudiation** | "I never approved that" | Audit log with actor, IP, user agent; MFA step-up on approval |
| **Information disclosure** | Cross-jurisdiction data | Server-side scope filter on every query; RBAC matrix test |
| **Information disclosure** | Signed URL sharing | 300 s TTL; single-use where the store supports it |
| **Denial of service** | Huge image uploads | 20 MB cap; `MAX_EDGE` downscale; per-user rate limit |
| **Denial of service** | Decompression bomb | Pillow `MAX_IMAGE_PIXELS` cap; dimension check before decode |
| **Elevation of privilege** | Role escalation | Role changes are `ADMIN`-only, audited, and revoke all sessions |
| **Supply chain** | Malicious dependency | Pinned lockfiles, digest-pinned bases, `pip-audit`/`npm audit`/Trivy in CI |

### 20.2 Upload validation

Order is mandatory: size cap → MIME **and magic-byte** check → dimension sanity
(≤ 100 MP) → decode in a resource-limited subprocess → virus scan (ClamAV) → EXIF strip →
persist. A file failing any step is rejected with `E_UNSUPPORTED_MEDIA` and never stored.

### 20.3 Transport and storage

TLS 1.2+ (prefer 1.3) everywhere; HSTS with preload on the console; encryption at rest for
database and object storage; secrets from a secrets manager injected as environment
variables, never baked into images.

### 20.4 Application hardening

Pydantic validation on every input; parameterised queries only (no string-built SQL);
CSP with no `unsafe-inline`; `X-Content-Type-Options: nosniff`; `Referrer-Policy:
same-origin`; CORS restricted to known console origins; CSRF protection on cookie-based
flows.

### 20.5 Legal-defensibility controls

Beyond ordinary security, because outputs may be used in enforcement:

1. Every verdict cites a rulepack hash and a law version.
2. Every override records actor, timestamp and reason, and never replaces the original.
3. Evidence images are immutable and hash-addressed from the moment of upload.
4. Execution manifests permit byte-identical replay (SC-6).
5. Chain-gap disclosures print on every report.
6. Reports carry a content hash and a version number.

---

## Part 21 — Testing strategy

### 21.1 Suites

| Suite | Command | Scope | Current |
|---|---|---|---|
| Unit + integration | `pytest -q` | Rulepack integrity, operators, temporal logic, adversarial fail-tests, spec/code and cross-document consistency | **176 collected; PostgreSQL cases run with `LMPC_TEST_DB_URL`** |
| Synthetic stress | `python -m stress.run` | 22 scenarios / 28 expectations, noise sweep, sensitivity sweep | passing |
| Validation campaign | `python -m stress.campaign` | 24 checks across ingestion, compilation, comparison | **24/24** |
| Real world | `python -m stress.realworld food\|wide` | 140 real products, 403 photographs | passing |
| Resolution | `python -m stress.resolution` | Time vs accuracy vs pixel budget | measured |
| RBAC matrix | `pytest tests/test_rbac.py` | Every role × every protected endpoint, plus fail-closed route inventory | **100 role/endpoint cells passing** |
| E2E | Playwright | Login → capture → review → finalise → download | **to build** |
| Load | k6 | Pilot-scale concurrency | **to build** |

### 21.2 Why labels are rendered, not photographed

Real photographs have no ground truth: nobody knows to a tenth of a millimetre how tall the
glyphs are, so any verdict about a 2.5 mm threshold is unfalsifiable. Synthetic labels are
rendered at a known DPI with a **measured** cap height, so the expected verdict is derived
from physics. Real photographs then supply the failure modes rendering cannot.

Both are mandatory. Neither is sufficient.

### 21.3 Acceptance gates — CI fails on any

| Gate | Bar | Measured |
|---|---|---|
| Scenario expectations | all met | 28/28 across 22 scenarios |
| False accusations on compliant labels | ≤ 2 % | **0 %** at 0–40 % character error |
| Violations silently passed | 0 | **0** |
| `FAIL` without asserted coverage | 0 | **0** in 2,700 real evaluations |
| Campaign checks | all pass | 24/24 |
| Every verdict carries clause + citation + reason | 100 % | 100 % |
| Glyph height error (when segmentation lands) | ≤ 0.15 mm | not yet built |
| Field identification on correctly captured packages | ≥ 90 % | **~50 % — SC-3 gap** |

### 21.4 Test data

| Set | Size | Purpose |
|---|---|---|
| Synthetic | generated per run | Exact ground truth for measurement checks |
| Gold (real) | 140 products, 403 images | Extraction accuracy, false-accusation guard |
| Adversarial | 24 fail-tests | The system must refuse, not guess |
| Corpora | 48 gazette instruments, 3 families | Compiler generalisation and collisions |

Corpora and photographs are **fetched, not committed** — they are reproducible inputs, not
source. Tests that need one skip with the command that produces it.

### 21.5 Definition of done for any new check

1. Rule text quoted from the gazette with file and page.
2. A binding with `confirmed_values` where numeric.
3. At least three fixtures: pass, fail, and abstain.
4. A stated refusal path — when the check declines to answer and why.
5. An entry in the Part 23 catalogue.
6. Sensitivity coverage: it still catches its violation under 10 % character error.

---

## Part 22 — Delivery plan and acceptance

Detailed sequencing lives in `03-ENGINEERING-PLAN.md`. This section defines the acceptance
gate per component.

| # | Component | Acceptance |
|---|---|---|
| 1 | Law compiler | `unverified_bindings` empty; chain complete or fully disclosed; build refuses in all 8 states |
| 2 | Guided capture | Unseen packet captured in ≤ 90 s on a mid-range Android browser; all frames pass gates; `coverage_asserted=true` reaches the server and re-validates |
| 3 | Extraction | ≥ 90 % identification on correctly captured packages with the false-accusation rate still 0 |
| 4 | Measurement | Glyph height error ≤ 0.15 mm over 20 calibration samples; non-coplanar marker abstains |
| 5 | Rule engine | 24/24 campaign; temporal replay reproduces a 2016 finding |
| 6 | Reports | PDF and DOCX identical in findings; content hash stable; correction round-trip retained and diffable |
| 7 | Console | RBAC matrix green; WCAG 2.1 AA on scan detail and approval; ScoreExplainer present |
| 8 | Mobile sync | Airplane-mode capture → reconnect → sync; duplicate submission creates no duplicate; conflict surfaces a merge screen |
| 9 | Platform | Restore drill passes; offline drill passes; P1 alerts verified by injection |

**Release criteria for the pilot:** components 1–9 accepted; SC-1 to SC-7 met or formally
waived with a recorded reason; every Part 25 question either closed or explicitly accepted
as a known limitation printed on reports.

---

## Part 23 — Rule catalogue

### 23.1 Applicability gates — evaluated first

| ID | Clause | Condition | Effect |
|---|---|---|---|
| `GATE-R3-BULK` | Rule 3(a)(b)(c) | > 25 kg or 25 L · cement, fertiliser or farm produce in bags > 50 kg · industrial or institutional buyer | Chapter II not applied |
| `GATE-R26-EXEMPT` | Rule 26 | ≤ 10 g / 10 ml (**tobacco carved out**) · restaurant or hotel fast food · DPCO formulations · handloom thread in coil | **All rules** not applied |
| `GATE-R26-DRUG-FORMULATION` | Rule 26(c) | DPCO drug formulation, unless a medical device declared as a drug | All rules not applied |
| `GATE-R7-5-OTHER-LAW` | Rule 7(5) | The same information is required by another law | Skip 7(1)–(4) **except** net weight, retail sale price, expiry/best-before/use-by, consumer care |

### 23.2 Checks

| ID | Clause | Operator | In force | Notes |
|---|---|---|---|---|
| `LMPC-R6-1-A-MANUFACTURER` | 6(1)(a) | presence | 2011-04-01 | Name and complete address |
| `LMPC-R6-1-B-GENERIC-NAME` | 6(1)(b) | presence | 2011-04-01 | **Ceiling `INDETERMINATE`** — no lexical anchor exists |
| `LMPC-R6-1-C-NET-QUANTITY` | 6(1)(c) | presence | 2011-04-01 | |
| `LMPC-R6-1-D-MFG-DATE` | 6(1)(d) | presence | 2011-04-01 | Excluded in e-commerce mode |
| `LMPC-R6-1-E-MRP` | 6(1)(e) | presence | 2011-04-01 | |
| `LMPC-R6-1-F-CONSUMER-CARE` | 6(1)(f) | presence | 2011-04-01 | Name, address, phone and/or email |
| `LMPC-R6-COUNTRY-OF-ORIGIN` | 6(1) | presence | 2011-04-01 | `only_when: is_imported` |
| `LMPC-R6-1-E-MRP-FORM` | 6(1)(e) | format_regex + phrase | 2018-01-01 | Four gazette illustrations; wording fuzzy, digits exact |
| `LMPC-R6-1-E-MRP-ROUNDING` | 6(1)(e) | numeric_predicate | 2018-01-01 | Nearest rupee or 50 paise |
| `LMPC-R6-1-C-QTY-FORM` | 6(1)(c) | format_regex | 2011-04-01 | Numeral + SI unit |
| `LMPC-R6-1-D-DATE-FORM` | 6(1)(d) | format_regex | 2011-04-01 | `MM/YYYY` or month name + year |
| `LMPC-R6-1-D-DATE-PLAUSIBLE` | 6(1)(d) | date_plausible | 2011-04-01 | Future or pre-commencement → `REVIEW_REQUIRED` |
| `LMPC-R10-PIN-CODE` | 10(1) Expl. 1 | format_regex | 2018-01-01 | Six-digit PIN in the address |
| `LMPC-R10-1-SMALL-PACKAGE-MARK` | 10(1) proviso | small_package_mark | 2018-01-01 | ≤ **10 cm³** (raised from 5 in 2017) |
| `LMPC-R6-1-LL-UNIT-SALE-PRICE` | 6(1)(ll) | tiered_format | 2022-04-01 | per g/kg/ml/litre/cm/m/number by quantity |
| `LMPC-R6-3-MRP-STICKER` | 6(3) | mrp_uniqueness | 2011-04-01 | Two prices → `REVIEW_REQUIRED`; a lower revised price is lawful |
| `LMPC-R9-4-LANGUAGE` | 9(4) | script_allowed | 2011-04-01 | Devanagari **or** Latin; a third script is never itself a violation |
| `LMPC-R7-3-WIDTH-RATIO` | 7(3) | ratio_min | 2018-01-01 | Width ≥ ⅓ height, excluding `1 i I l`; **needs glyph segmentation** |
| `LMPC-R8-CLEAR-SPACE` | 8 | clear_space | 2011-04-01 | ≥ 1× above/below, ≥ 2× left/right of the numeral |
| `LMPC-R7-2-MIN-HEIGHT` | 7(2) Table-I | table_lookup | 2011-04-01 | Versions in 23.3 |
| `LMPC-XF-UNIT-PRICE-CONSISTENT` | 6(1)(ll) | cross_field | 2022-04-01 | ±5 % of MRP ÷ quantity, else `REVIEW_REQUIRED` |

### 23.3 Rule 7 Table-I

**Current — G.S.R. 629(E) page 11, in force 2018-01-01:**

| PDP area A (cm²) | Minimum height | Blown / formed / moulded |
|---|---|---|
| A < 50 | 1.0 mm | 1.5 mm |
| 50 < A < 100 | 1.5 mm | 3.0 mm |
| 100 < A < 500 | 2.5 mm | 4.0 mm |
| 500 < A < 2500 | 4.0 mm | 6.0 mm |
| 2500 < A | 6.0 mm | 6.0 mm |

**Table-II was omitted** by the same amendment. All five boundary operators carry
`needs_human_confirmation: true` — the embedded font drops `≤`.

**Repealed — retained for inspections before 2018-01-01, keyed to net quantity:**

| Net quantity | Minimum height |
|---|---|
| ≤ 200 g/ml | 1.0 mm |
| ≤ 1 kg/l | 2.0 mm |
| above | 4.0 mm |

### 23.4 Rule 7(4) — principal display panel area

| Shape | Area |
|---|---|
| Rectangular, one side clearly the PDP | height × width of that side |
| Cylindrical or nearly cylindrical | **0.40 × height × circumference** |
| Any other shape | 0.40 × total surface area |

Excluding the top, the bottom, flanges at the top and bottom of cans, and the shoulders and
necks of bottles and jars.

### 23.5 Rule 6(1)(e) — permitted MRP forms

Four illustrations from the 2017 amendment, page 10:

```
Maximum or Max. retail price Rs. xx.xx (inclusive of all taxes)
Maximum or Max. retail price Rs. xx.xx inclusive of all taxes
MRP Rs. xx.xx incl. of all taxes
MRP Rs. xx.xx (incl. of all taxes)
```

The price MUST be rounded to the nearest rupee or 50 paise.

### 23.6 Rule 6(1)(ll) — unit sale price tiers

| Condition | Required form |
|---|---|
| Weight < 1 kg | `Rs. _ per g` |
| Weight ≥ 1 kg | `Rs. _ per kg` |
| Length < 1 m | `Rs. _ per cm` |
| Length ≥ 1 m | `Rs. _ per meter` |
| Volume < 1 l | `Rs. _ per ml` |
| Volume ≥ 1 l | `Rs. _ per litre` |
| Sold by number | `Rs. _ per number` |

### 23.7 Rule 6(10) — e-commerce

All declarations required by Rule 6(1) **except the month and year of manufacture or
packing**. Excluded checks: `LMPC-R6-1-D-MFG-DATE`, `LMPC-R6-1-D-DATE-FORM`,
`LMPC-R7-2-MIN-HEIGHT`, `LMPC-R7-3-WIDTH-RATIO`, `LMPC-R8-CLEAR-SPACE`.

### 23.8 Deferred with reason

| Rule | Why deferred |
|---|---|
| 6(3) sticker physically covering the original MRP | Needs tamper/overlay detection, not text |
| 9(1)(b) contrast of RSP and net-quantity numerals | Needs colour sampling from the glyph mask |
| 9(2) declaration readable through a liquid | Needs 3D reasoning |
| 9(3) outer container declarations | Needs an explicit outer/inner capture flow |
| 2022 garments size indicators | Needs textile category data not currently captured |

---

## Part 24 — Defect register

Twenty defects found by testing. Each was working code reaching a wrong legal
conclusion; none was visible from reading the code.

| # | Defect | Found by | Fix |
|---|---|---|---|
| M.1 | Verdict ceiling suppressed **every** font violation, not only boundary cases | synthetic stress | Ceilings name what they cap |
| M.2 | Absence concluded from an unreadable image — **60 % of compliant labels accused** at 5 % error | noise sweep | Absence needs legible evidence + near-miss check |
| M.3 | Format checks failed on OCR damage (`MRP Rs. 4S.00`) | noise sweep | Scoped repair; match-after-repair → `INDETERMINATE` |
| M.4 | Global repair corrupted neighbours: `Rs.`→`R5.`, `incl.`→`inc1.` | noise sweep | Repair only inside numeric runs |
| M.5 | Legal wording matched exactly; `incl. of gll taxes` failed a compliant label | noise sweep | Wording fuzzy, digits exact |
| M.6 | One threshold for all claims: false accusations or silent misses | sensitivity sweep | Three thresholds (P5) |
| M.7 | Partial parse passed an unrounded price: `45.b0` → `45.0` | sensitivity sweep | Numeral must be consumed end to end |
| M.8 | **Instrument identity was the number alone** — `G.S.R. 875(E)` exists in 2016 **and** 2025, both cited as predecessors | second rule family | Identity = (number, year) |
| M.9 | `G`→`6` repair turned `MFG02/2025` into `MF 602/2025` | real corpus | Mapping removed |
| M.10 | Rule families merged; the walk picked an arbitrary root and invented gaps | second rule family | Transitive family resolution |
| M.11 | **Effective dates ignored entirely** — a 2016 package judged by 2018 law | time-travel test | Temporal filter + retained repealed tables |
| M.12 | One corrupt PDF killed the entire build | adversarial | Unreadable files recorded and excluded |
| M.13 | `built_at` inside the hashed body made builds non-reproducible | adversarial | Hash first, stamp after |
| M.14 | **64 MP photos exhausted memory and never returned**; two fix attempts silently no-oped | real photographs | `MAX_EDGE` cap; every edit asserted |
| M.15 | Width ratio measured detection-box height → **11 false accusations** at plausible values; also measured `A QUALITY PRODUCT OF` | real photographs | Abstain without glyph segmentation; declarations only |
| M.16 | Third-party image labels treated as coverage → declarations "missing" on unphotographed sides | wide real-world | `coverage_asserted` (P4) |
| M.18 | **Every "GPU" measurement was actually CPU.** `onnxruntime` advertises `CUDAExecutionProvider` with no CUDA runtime present and falls back silently; the spec's "GPU is not optional" claim rested on it | model-swap investigation | Probe a real session, not the provider list; claim corrected |
| M.19 | **The OCR model cannot emit Devanagari.** The shipped default is the *Chinese* recogniser; "Hindi untested" was really "Hindi impossible" | model-swap investigation | Ship `en` + `devanagari` specialist recognisers |
| M.20 | The synthetic Hindi label was rendered in DejaVu Sans, which has **no Devanagari glyphs** — the scenario tested tofu, not Hindi | model-swap investigation | Devanagari text renders with Noto Sans Devanagari |
| M.17 | **Our own repair manufactured a PASS**: respacing `4S.3s` → `4 S.3 s` let the parser read `4`, call it rounded, and pass an unrounded price | campaign regression | Value judgements forbidden on repaired text (P9) |

**The pattern.** Five separate times a check answered confidently from a measurement it
should not have trusted (M.2, M.7, M.15, M.16, M.17). The fifth was caught by the campaign
after the previous version of this specification was written, not by a unit test.
**Assume a sixth exists.** Every new check ships gated on the trustworthiness of its own
measurement (21.5).

---

## Part 25 — Open questions

| # | Question | Blocks | Owner | Due |
|---|---|---|---|---|
| 25.1 | ~⅓ of amendment operations resolve to `lmpc/?` — the rule number sits in a preceding sentence | Full automatic consolidation | Compiler owner | Week 2 |
| 25.2 | 12 bindings trace to the base 2011 rules, which are an un-OCR'd bilingual scan | Emptying `unverified_bindings` | Legal pair | Week 2 |
| 25.3 | `<` vs `≤` at all four Table-I boundaries; the text layer drops `≤` | Rule 7(2) near boundaries | Legal reviewer | Week 1 day 3 |
| 25.4 | Devanagari letter height — is the shirorekha included? | Rule 7(2) on Hindi labels | Legal reviewer | Week 1 day 5 |
| 25.5 | **Hindi is impossible today, not merely untested** — the shipped recogniser is the Chinese model (M.19). Ship `en` + `devanagari` recognisers, measure the per-region selection policy against a labelled Hindi set, and fix matra/spacing errors | Rule 9(4) and all Hindi extraction | Vision owner | **Week 1** |
| 25.6 | Glyph segmentation for Rule 7(3) — billed as "build first, no calibration needed", which was wrong | Rule 7(3) verdicts | Vision owner | Week 4 |
| 25.7 | MRP identified on ~50 % of packets where it is legible | SC-3, and shipping | Extraction owner | Week 3 |
| 25.8 | Image retention period against departmental records policy | Part 13.6 | Programme | Before pilot |
| 25.9 | Whether a single-officer office may self-review (`ALLOW_SELF_REVIEW`) | Part 15.5 | Department | Before pilot |
| 25.10 | Qualified Legal Metrology officer for rulepack sign-off | Production use | Programme | Before pilot |
| 25.11 | Recogniser upgrade path. Ship `en` + `devanagari` PP-OCRv3 specialists immediately (nearly free, unblocks Hindi); then evaluate PP-OCRv5 mobile and server variants against a labelled Indian set measuring accuracy **and** seconds per photo on target hardware. Surya is excluded: it declares `openai` as a dependency and would fail the P8 CI check | SC-3 | Vision owner | Week 2 |

---

## Appendix A — Error codes

| Code | HTTP | Meaning |
|---|---|---|
| `E_VALIDATION` | 400 | Request failed schema validation |
| `E_REASON_REQUIRED` | 400 | Override reason shorter than 10 characters |
| `E_BOUNDARY_UNCONFIRMED` | 400 | Rulepack approval attempted with unconfirmed boundaries |
| `E_BAD_CREDENTIALS` | 401 | Unknown user or wrong password |
| `E_TOKEN_EXPIRED` | 401 | Access token expired |
| `E_REFRESH_REVOKED` | 401 | Refresh token revoked or reused |
| `E_MFA_REQUIRED` | 403 | Second factor required |
| `E_STEP_UP_REQUIRED` | 403 | Recent MFA required for this action |
| `E_FORBIDDEN` | 403 | Role or jurisdiction does not permit this |
| `E_NOT_FOUND` | 404 | Absent, or outside the caller's scope |
| `E_SCAN_FINALIZED` | 409 | Mutation attempted on a finalised scan |
| `E_COVERAGE_MISMATCH` | 409 | `coverage_asserted=true` with panels missing |
| `E_CONFLICT` | 409 | Optimistic concurrency failure; server state returned |
| `E_IMAGE_TOO_LARGE` | 413 | Image exceeds 20 MB |
| `E_UNSUPPORTED_MEDIA` | 415 | Failed MIME, magic-byte or dimension validation |
| `E_RATE_LIMITED` | 429 | Rate limit exceeded; `Retry-After` set |
| `E_RULEPACK_INTEGRITY` | 503 | Rulepack failed its integrity check; service not ready |
| `E_INTERNAL` | 500 | Unhandled; correlation ID returned |

## Appendix B — Configuration reference

| Variable | Default | Component |
|---|---|---|
| `LMPC_DB_URL` | — | api, workers |
| `LMPC_REDIS_URL` | — | api, workers |
| `LMPC_S3_ENDPOINT` / `_BUCKET` / `_KEY` / `_SECRET` | — | api, workers |
| `LMPC_RULEPACK_PATH` | `/srv/rulepack/current.json` | api, worker-rules |
| `LMPC_OCR_MAX_EDGE` | `1800` | worker-ocr |
| `LMPC_OCR_DEVICE` | `auto` | worker-ocr |
| `LMPC_OCR_MODEL_DIR` | `/opt/models` | worker-ocr |
| `LMPC_ACCESS_TOKEN_TTL` | `900` | api |
| `LMPC_REFRESH_TOKEN_TTL` | `2592000` | api |
| `LMPC_OIDC_ISSUER` / `_CLIENT_ID` / `_CLIENT_SECRET` | — | api, web |
| `LMPC_ALLOW_SELF_REVIEW` | `false` | api |
| `LMPC_RATE_LIMIT_PER_MIN` | `60` | api |
| `LMPC_MAX_IMAGE_BYTES` | `20971520` | api |
| `LMPC_MAX_IMAGE_PIXELS` | `100000000` | api, worker-ocr |
| `LMPC_LOG_LEVEL` | `INFO` | all |
| `LMPC_OTEL_ENDPOINT` | — | all |

## Appendix C — Glossary

| Term | Meaning |
|---|---|
| **Coverage assertion** | The capture flow's confirmation that every required surface was photographed. Without it, absence cannot become a violation (P4) |
| **Gate** | An applicability rule evaluated before any check; a fired gate ends evaluation |
| **G.S.R.** | General Statutory Rules — the numbering of a gazette notification. Restarts annually (P2) |
| **Instrument** | One gazette notification |
| **LMPC** | Legal Metrology (Packaged Commodities) Rules, 2011 |
| **Node address** | A stable address in the rule tree, e.g. `lmpc/r7/table-I`. Bindings attach here, not to values |
| **PDP** | Principal Display Panel — the face bearing the mandatory declarations |
| **Provenance (`src`)** | Which raw OCR regions a candidate was assembled from; used to keep the margin test honest |
| **Rulepack** | The compiled, versioned, hash-addressed representation of the law |
| **Verdict ceiling** | A cap preventing a check from reaching `FAIL`, where law or measurement does not support accusation |

## Appendix D — Repository layout

```
lmpc/
  lawc/       parse.py · build.py · bindings.yaml · gaps.yaml
              fetch.sh (Packaged Commodities) · fetch-general.sh (General Rules, GATC)
  engine/     model.py · ocr.py · layout.py · lexicon.py · normalize.py
              extract.py · operators.py · engine.py · report.py
  labels/     generate.py (synthetic, exact ground truth) · openfoodfacts.py (real photos)
rulepack/     current.json  (generated; hash-addressed; tracked so checkout runs)
stress/       run.py · campaign.py · realworld.py · resolution.py · scenarios.py
tests/        test_rulepack.py · test_engine.py · test_adversarial.py · test_stress.py
docs/         00-TEAM-BRIEF · 01-ARCHITECTURE · 02-BUILD-SPEC · 03-ENGINEERING-PLAN
              04-FLOW · 05-SYSTEM-MAP · 06-RULEPACK
              evidence/ · archive/ · source-extracts/
corpus/           Packaged Commodities gazettes  (git-ignored; fetch.sh)
corpus_general/   General Rules + GATC gazettes  (git-ignored; fetch-general.sh)
real/             harvested product photographs  (git-ignored; lmpc.labels.openfoodfacts)
```

## Appendix E — Document control

| Version | Date | Change |
|---|---|---|
| 1.0 | Sep 2026 | Initial draft — superseded; rule values were wrong against the notified law |
| 2.0 | 2026-09-07 | Consolidated after validation; 17 defects catalogued |
| 3.0 | 2026-09-07 | Full engineering specification: API, schema, auth, RBAC, console, mobile, infrastructure, observability, security, testing, delivery |
| 3.1 | 2026-09-08 | Cross-document consistency enforced in CI (18.4 §8b). Client/server split traced to the problem statement (3.5). Three defects corrected: the recogniser cannot emit Devanagari (M.19); every "GPU" figure was CPU and a GPU is **not** required (M.18); synthetic Hindi rendered in a font with no Devanagari glyphs (M.20). Recogniser upgrade path recorded (25.11) |

**Review cadence.** This document MUST be reviewed whenever a new rulepack is approved,
whenever a Part 25 question closes, and at each release tag. A change to any measured value
MUST cite the run that produced it.
