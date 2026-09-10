# SIH idea-pitch deck — research notes

Sources consulted (see `sources.md` for links) plus the two sample decks in
`reference_ppt/` (SIH 2025 PS SIH25017 title page; SIH 2024 PS1628 "PlaceX" full deck).

## Judging rubric (finale, from a documented SIH 2024 journey)

Score = **0.4 × relevancy + 0.3 × feasibility + 0.3 × attractiveness**.

- *Relevancy* — does the idea solve THIS problem statement, for the named end users?
  Worth the most; map every feature to a PS requirement explicitly.
- *Feasibility* — buildable with current tech, viable as a product.
- *Attractiveness* — prototype/demo quality and the pitch itself.

## Official template constraints (from template.pptx)

7 slides total, **max 6 content slides**; slide 1 is the fixed TITLE PAGE boilerplate
(Problem Statement ID, Theme, PS Category, Team ID/Name, Institute); slide 7 is the
instruction slide. Use the provided template without changing the idea-detail pointers.
Points, diagrams and infographics preferred over paragraphs.

## Slide plan (6 content slides)

1. **Problem** — quantified: retail packages declare MRP/net quantity/manufacturer on
   the pack; verification is manual, per-officer, and the law changes by amendment.
   Cite the PS wording, not our solution.
2. **Solution in one line + architecture** — gazette PDFs → law compiler → hashed
   rulepack; label photo → OCR → deterministic rule engine → six-verdict finding.
   Diagram, not prose. No LLM anywhere.
3. **How it solves the PS** — map to the PS requirements: web/mobile app, repository of
   scans, dashboards, search, RBAC, deployable. One bullet each, explicitly labelled.
4. **Novelty / uniqueness** — law is *compiled* from primary gazette text (versioned,
   hashed, dated), not hardcoded; six verdicts, not two — "could not read" ≠ "missing";
   0 false accusations by design; findings reproducible years later (temporal law).
5. **Evidence & feasibility** — corrected numbers from `docs/evidence/` only: 140 real
   products / 403 photos, 2,700 evaluations, 0 false accusations,
   1.6 s/panel on CPU. Tech stack line.
6. **Impact + roadmap + demo** — beneficiaries (Legal Metrology officers, consumers,
   MSMEs), 6-month roadmap, demo screenshot/QR.

## Winner advice incorporated

- Demo > slides: one working scan with a violation and its evidence crop beats any
  feature list; the deck carries the same evidence box as the demo.
- Say the PS number and theme on the title slide (common miss).
- Preempt jury questions: data privacy (images on-prem, GPS stripped), cost (runs on
  commodity hardware, CPU), adoption (officer phone + browser, no app store).
- One result card, big: a FAIL with measurement, clause citation and rulepack version.
- The "killer" comparison: repealed Table-I (2011, p.47 scan) vs the 2017 gazette that
  replaced it — proves the amendment-tracking story in one image.
