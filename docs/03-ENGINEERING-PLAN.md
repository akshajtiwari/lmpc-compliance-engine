# Engineering Plan

**Version 2.0 · 2026-09-07.** Supersedes v1.0, which was written before any of it was
tested. Every estimate here is anchored to a measurement in `docs/evidence/`.

**Companion:** `02-BUILD-SPEC.md` is the implementation document. This one answers *what
gets built, by whom, in what order, and what must be true before we move on.*

---

## 1. Where we actually are

A working prototype exists and has been validated against live data. This is not a
proposal; it is a report on a partly-built system.

| | Status |
|---|---|
| Law compiler | **Working.** 48 gazette instruments, 3 rule families, chains reconstructed |
| Rulepack | **Working.** 21 checks, 4 gates, hash-addressed, current to G.S.R. 418(E) (29 May 2026) |
| Rule engine | **Working.** 6 verdict states, temporal selection, 12 operators |
| Extraction | **Weak.** MRP found on ~50 % of packets where it is legible |
| Capture app | **Local MVP working.** Guided panels, measurable quality gates, offline outbox and retry-safe sync |
| Web console | **Partial.** Capture, evidence, scoped server search, dashboard summary, corrections, overrides and report export work; rule/user administration remains |
| Reports, repository, auth | **Working locally.** PostgreSQL, searchable/scoped history, append-only correction/override, reports, Argon2id/RS256 sessions and route RBAC; OIDC/MFA remain |
| Tests | 150 collected unit/integration · 22 scenarios (28 expectations) · 24 campaign checks · 140 real products |

**Validated behaviour:** 0 false accusations in 2,700 real rule evaluations; 0 violations
silently passed; 0 % false-FAIL rate on compliant labels across 0–40 % simulated character
error.

---

## 2. What testing changed about the plan

Five conclusions that reverse or sharpen v1.0.

**2.1 Guided capture is the highest-value component, not a nicety.**
On 48 of 60 real food products the MRP was never photographed. No model fixes that. The
code now *refuses to issue a violation* without an explicit coverage assertion, so the
capture app is on the critical path for the system to produce any finding at all.

**2.2 The law is compiled, and that part is done.**
v1.0 said "two people read the law and type YAML". That objection was correct and the
answer is built: a compiler that fetches, orders, parses and cross-checks. The recurring
cost per amendment is approving a diff.

**2.3 Rule 7(3) is not free.**
The team brief said the width-ratio and clear-space checks need no calibration, so build
them first. Half of that was wrong: Rule 7(3) needs **per-letter** measurement, which
detection boxes cannot provide, and it produced 11 false accusations before it was gated.
Budget glyph segmentation or drop the check.

**2.4 A GPU is optional; the resolution cap is what mattered.**
This previously read "the server needs a GPU", on the strength of timings that turned out
to be CPU all along — `onnxruntime` advertises CUDA even with no CUDA runtime installed and
falls back silently (M.18). **CPU manages 1.6 s per panel**, comfortably inside the budget.
The original unbounded runtimes were caused by feeding 64 MP frames to the recogniser, not
by missing hardware. Recognition still happens server-side; the client only captures.

**2.5 Assume a further measurement bug.**
Five separate times a check answered confidently from a measurement it should not have
trusted (M.2, M.7, M.15, M.16, M.17). The fifth was found *after* the spec was written, by
the campaign rather than by unit tests — our own OCR repair respaced `4S.3s` into `4 S.3 s`
and passed an unrounded price. Every new check ships gated on the trustworthiness of its
own measurement, and the campaign runs in CI.

---

## 3. Scope

| # | Problem-statement requirement | v1 | How |
|---|---|---|---|
| 1 | Image upload / scanning | BUILD | Guided PWA capture with on-device quality gates |
| 2 | Extraction of declarations | BUILD | PP-OCR → layout assembly → scored rubric |
| 3 | Detect mandatory declarations | BUILD | 7 presence checks |
| 4 | Correctness and completeness | BUILD | 8 format + consistency checks |
| 5 | Placement | PARTIAL | Rule 8 clear space on flat panels; curved abstains |
| 6 | Font size and readability | PARTIAL | Rule 7(2) with a scale reference; Rule 7(3) blocked on N.6 |
| 7 | Missing / misleading / non-standard | PARTIAL | **"Misleading" is a named non-goal** — it needs facts off the label |
| 8 | Reports, PDF + editable | BUILD | One verdict object → WeasyPrint + docxtpl |
| 9 | Photographs and evidence | BUILD | Immutable originals, SHA-256, annotated crops |
| 10 | Repository, search, history | BUILD | Postgres + `pg_trgm` |
| 11 | Role-based access | BUILD | 4 roles, server-side, jurisdiction-scoped |
| 12 | Dashboards | BUILD | Enforcement workbench, not a charts page |
| 13 | Product listings / e-commerce | PARTIAL | Paste listing text + screenshots; Rule 6(10) subset; **no crawler** |
| 14 | Technical documentation | **DONE** | `docs/` + evidence reports |

**Named non-goals:** verifying that a declared MRP is the true MRP · net-content weighing ·
scripts beyond English and Hindi · automatic rule publication · any language model in the
product · blockchain · Kubernetes.

---

## 4. Workstreams

Dependencies are hard. Nothing downstream starts on a guess about an upstream contract.

### W1 — Law compiler and rulepack ✅ *substantially complete*
Remaining: close N.1 (node resolution), N.2 (OCR the 2011–2015 scans so the base rules
enter the corpus and `unverified_bindings` empties), N.3 (`<` vs `≤` ruling).
**Done when:** `unverified_bindings` is empty and the chain is complete or fully disclosed.

### W2 — Guided capture *(critical path)*
State machine (B.1), on-device quality gates (B.2), coverage assertion (B.3), scale
reference capture (B.4), resumable upload, offline queue with `client_uuid`.
**Done when:** an officer photographs an unseen packet in under 90 s on a mid-range Android
browser, every frame passes the gates, and `coverage_asserted=true` reaches the server.

### W3 — Extraction quality *(the measured gap)*
Improve on the current ~50 %: better line assembly, per-field spatial association, a
larger lexicon, Devanagari coverage, and a labelled evaluation set from real packets.
**Done when:** ≥ 90 % of mandatory declarations are identified on correctly photographed
packets, with the false-accusation rate still at 0.

### W4 — Vision and measurement
Scale-reference detection and homography, PDP area from measured dimensions, glyph
segmentation for Rule 7(3) (N.6), curved-surface abstention.
**Done when:** glyph height error ≤ 0.15 mm on a printed calibration sheet over 20 samples,
and a non-coplanar marker abstains.

### W5 — Reports and repository
PDF + DOCX from one verdict object, report hashing and versioning, product dedup, search,
CSV export, execution manifest.
**Done when:** an officer corrects an extraction, re-runs, and both runs are retained and
diffable; PDF and DOCX carry identical findings and the rulepack hash.

### W6 — Console, auth, dashboards
Evidence overlay viewer, `ScoreExplainer`, override with reason, RBAC, jurisdiction
filtering, amendment quarantine queue, aggregate views.
**Done when:** the RBAC matrix (every role × every endpoint) returns correct 200/403 and no
endpoint relies on UI hiding.

### W7 — E-commerce variant
Listing text paste, gallery screenshots, Rule 6(10) subset.
**Done when:** the same package in both modes differs only by the packing-date rule
returning `NOT_APPLICABLE`.

### W8 — Hardening and pilot
Load test, accessibility pass, offline drill, backup/restore, security review, pilot with a
real enforcement unit.

---

## 5. Schedule and gates

A gate is not a status meeting. If its criteria fail, the following week's scope is cut.

| Wk | Focus | Gate |
|---|---|---|
| 1 | Close W1 loose ends; start W2 | `unverified_bindings` empty; N.3 ruled or guard band documented; capture state machine demoed |
| 2 | W2 capture; W3 begins | A real packet captured end to end with `coverage_asserted=true`; **Hindi labels collected** (N.5) |
| 3 | W3 extraction | ≥ 90 % identification on correctly photographed packets; false accusations still 0 |
| 4 | W4 measurement; W5 reports | Rule 7(2) verdict with a CI and a gazette citation on screen; PDF + DOCX export |
| 5 | W6 console and auth | RBAC matrix green; override round-trip retained and diffable |
| 6 | W7 + W8 hardening | Campaign green; offline drill; pilot deployment |

**Freeze rulepack, model files and container digests before the finale.**

---

## 6. Risk register

| Risk | L | Impact | Mitigation |
|---|---|---|---|
| Extraction stays near 50 % | **High** | System finds little | W3 is a full workstream with a measured bar, not a side task |
| Officers photograph the wrong panel | **High** | No findings at all | Guided capture refuses to advance; coverage assertion enforced in code |
| A sixth measurement bug | **High** | False accusation | Every check gated on its own measurement trustworthiness; campaign in CI |
| Hindi unvalidated | Med | Half the country's labels | N.5 promoted to a Week 2 gate |
| Repealed law reaches the rulepack | Low | Fatal to credibility | Compiler cross-checks values; build fails on drift |
| A 2026 amendment lands mid-build | Low | Currency claim breaks | Chain walk + quarantine; an unapproved amendment in quarantine is a demo asset |
| Latency on modest departmental hardware | Low | Budget blown | Measured at 1.6 s/panel on an ordinary CPU; `MAX_EDGE` is the tuning lever, and a GPU is available headroom if needed |
| Scope creep into "misleading" | Med | Unfalsifiable claims | Named non-goal; report states what was and was not checked |

---

## 7. Definition of done

1. Every verdict shows outcome · measured value with interval · required threshold · rule
   and sub-rule · gazette file, page and hash · rulepack version and hash · the evidence
   crop it was computed from.
2. No verdict exists that a person cannot trace to plain Python they can read.
3. No language model exists in the deployed system.
4. A package photographed incompletely returns `INDETERMINATE`, never `FAIL`.
5. **No `FAIL` is ever issued with `coverage_asserted=false`** — monitored and alertable.
6. An exempt package returns `NOT_APPLICABLE` with the exempting clause cited, before any
   declaration check runs.
7. A scan is judged by the law in force on its capture date; a later amendment cannot
   rewrite an earlier finding.
8. Reports export to PDF and DOCX with identical findings and a content hash.
9. The system runs with the government source unreachable.
10. A newly discovered notification is visible in quarantine, unapproved.

---

## 8. Evidence index

| Document | What it establishes |
|---|---|
| `evidence/LAW-COMPILER-TEST.md` | The law can be compiled automatically from live sources |
| `evidence/END-TO-END-STRESS-TEST.md` | Verdict behaviour under OCR noise; 7 defects |
| `evidence/VALIDATION-CAMPAIGN.md` | 24 checks across ingestion, compilation, comparison; 5 architectural defects |
| `evidence/REAL-WORLD-TEST.md` | 60 real food products; 5 defects |
| `evidence/WIDE-REAL-WORLD-TEST.md` | 80 more products across 4 categories; 3 defects; resolution budget |
