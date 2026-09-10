# LMPC Compliance — SIH pitch deck outline (draft for approval)

Format: 7 slides, 16:9. Slide 1 is the SIH title page; slides 2–7 are the six concise
content slides. Unknown submission metadata remains clearly marked for the team to fill.

## Slide 1 — Title page

- Legal Metrology Packaged Commodity Compliance Engine
- One-line promise: photograph a package; receive a legally traceable, deterministic finding
- Placeholders: Problem Statement ID, theme, category, team ID/name, institute
- Layout role: cover; official SIH identity first, product promise second
- Visual idea: a package silhouette intersected by a camera frame and a verified rulebook seal
- Required source images: none

## Slide 2 — The enforcement gap

- Officers manually inspect small declarations spread across every package surface
- A missing photograph can be mistaken for a missing declaration
- The governing rules change through amendments; an obvious base PDF can be out of date
- Manual evidence, citations, and repeatability make field decisions slow and difficult to audit
- Layout role: problem/context; four connected failure points leading to enforcement risk
- Visual idea: field inspection journey with the amendment timeline breaking across it
- Required source images: none

## Slide 3 — One system, two deterministic pipelines

- Offline: 48 gazette instruments → compiler → human-reviewed, versioned, SHA-256 rulepack
- Per scan: guided photos → OCR → layout/extraction → rule engine → six-state verdicts
- OCR supplies evidence; ordinary Python rules make every legal conclusion
- One localhost-capable FastAPI service powers the capture PWA and officer workbench
- Layout role: architecture/process; make the separation between law compilation and live scans unmistakable
- Visual idea: two-lane architecture joined only by the signed rulepack
- Required source images: none

## Slide 4 — Why the answer can be trusted

- Six verdicts distinguish PASS, FAIL, INDETERMINATE, NOT APPLICABLE, REVIEW, and SYSTEM ERROR
- “Could not read” never becomes “missing” until the guided capture confirms coverage
- Applicability gates run before declaration checks, preventing accusations against exempt packages
- Every result retains the rulepack version, authority citation, evidence hash, and evaluation history
- Corrections and officer overrides are append-only and attributed
- Layout role: novelty/trust model; compare unsafe binary automation with evidence-bound decisions
- Visual idea: a central FAIL finding card surrounded by evidence, clause, coverage, and provenance guards
- Required source images: none

## Slide 5 — Built for the complete problem statement

- Installable mobile PWA for guided, offline-resilient multi-panel capture
- Searchable inspection repository with jurisdiction-scoped RBAC
- Officer review workbench for corrections, re-evaluation, and reasoned overrides
- Dashboard for volume, violations, quality, and false-accusation guard breaches
- Immutable local object storage plus exportable PDF and DOCX reports; S3 remains optional
- Layout role: requirement mapping; explicit PS need → implemented capability pairs
- Visual idea: phone and workbench views connected to one local server
- Required source images: none for outline approval; a real app screenshot may be captured later if requested

## Slide 6 — Evidence, not promises

- 140 real products across food, cosmetics, household, and pet-food categories
- 403 real photographs and 2,700 deterministic rule evaluations
- 0 false accusations and 0 known violations silently passed in the recorded campaign
- 20 defects discovered and fixed through real-world and adversarial testing
- Approximately 1.6 seconds per panel on ordinary laptop CPU at the tested 1800 px cap
- Layout role: data evidence; one dominant “0 false accusations” result with four supporting proof points
- Visual idea: restrained metric wall plus confidence/abstention boundary graphic
- Required source images: none

## Slide 7 — Deployment, impact, and live demo close

- Runs today on localhost: Windows portable EXE for demos; PostgreSQL + local objects for durable use
- No S3 dependency in the current deployment; originals and reports stay on the controlled machine
- Beneficiaries: Legal Metrology officers, consumers, compliant brands, and MSMEs
- Demo sequence: guided capture → evidence-backed verdict → officer review → signed PDF/DOCX export
- Next steps: officer validation, wider multilingual testing, signed rulepack publication, controlled pilot
- Layout role: feasibility/close; deployment path and 90-second demo storyboard
- Visual idea: three-stage “run now → pilot → scale” path ending in a QR/link to the release
- Required source images: none for outline approval; release QR can be generated after the release URL exists

## Evidence and source guardrails

- Quantitative claims use the corrected figures in `README.md` and `docs/evidence/`.
- The deck will say that production legal use requires qualified officer sign-off.
- No slide will claim that an LLM makes compliance decisions.
- No slide images or PPTX are generated until this outline, a visual style, an image backend,
  and one representative sample slide have each been approved.
