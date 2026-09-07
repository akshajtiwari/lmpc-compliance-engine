# Validation Campaign — Should We Approve This Architecture?

**Run:** 2026-09-07 · `python -m stress.campaign` · `pytest -q`
**Data:** live, from `consumeraffairs.gov.in`, current to **G.S.R. 418(E), 29 May 2026**
**Scope:** the whole rulepack path — taking the data, making it comparable, and comparing.

---

## Verdict

**The architecture holds. Approve it — with the five conditions in §5.**

| | |
|---|---|
| Campaign checks | **24 of 24 passed** |
| Test suite | **44 passed** |
| Corpora | 30 Packaged Commodities + 18 General Rules / GATC instruments, fetched live |
| Defects found and fixed | **12** — 5 architectural, 7 in the comparison layer |
| False accusations on compliant labels | **0%**, character error 0 → 40% |
| Violations silently passed | **0** |

The important result is not the pass count. It is that **five defects were architectural**
— they would have survived any amount of unit testing and only appeared when the system
met a second rule family, a second decade, and a corrupt file.

---

## 1. What was attacked, and what broke

### A. Taking the data

| Attack | Outcome |
|---|---|
| Live fetch, expired TLS, dead port 80 | 48/48 documents retrieved |
| Digital vs scanned classification | 22 of 30 machine-readable; all 8 scans (2011–15) excluded rather than half-parsed |
| **Run the parser on a rule family it has never seen** | 94% self-identified on General Rules + GATC — not overfit |
| **Two instruments with the same G.S.R. number** | **DEFECT 1** — see below |
| Three rule families in one corpus | **DEFECT 2** |
| Corrupt / truncated / empty PDF | **DEFECT 3** |
| Chain walked to the base rules | 12 links; the one hole is named, not skipped |

**DEFECT 1 — instrument identity was unsound.** G.S.R. numbers restart every year.
`G.S.R. 875(E)` is *both* the General Rules amendment of 9 Sep 2016 *and* the breath
analyser amendment of 28 Nov 2025 — and **both are cited as predecessors by different
instruments in the live corpus.** Keying the chain on the number alone would have spliced
a 2021 amendment onto a 2025 one: a nine-year error, silent, applied to real scans.
*Identity is now (number, year). Collisions are detected and reported.*

**DEFECT 2 — rule families were merged.** One corpus holds Packaged Commodities, General
Rules and GATC, with independent chains. Merged, the walk picked an arbitrary root and
reported gaps that were not gaps. Families are now resolved **transitively** — an
amendment of an amendment belongs to the principal rules it ultimately amends. General
Rules went from 4 reconstructed links to 13.

**DEFECT 3 — one corrupt file killed the whole build.** A single bad download would have
taken down the rulepack. Unreadable files are now recorded as such and excluded — never
half-parsed, because a partially recovered gazette is worse than a missing one.

### B. Making it comparable

| Attack | Outcome |
|---|---|
| Gazette values vs reviewer-confirmed values | Cross-checked; **build fails on drift** (tested) |
| Chain hole with no acknowledgement | Build refuses (tested) |
| Disclosure covering a node we actually check | Build refuses (tested) |
| Gap acknowledged with no named reviewer | Build refuses (tested) |
| Same corpus, two builds | **DEFECT 4**, now identical hashes |
| Rulepack edited on disk | **DEFECT 5**, now rejected at load |
| Threshold quietly weakened to 0.1 mm | Rejected at load (tested) |

**DEFECT 4 — the build was not reproducible.** A `built_at` timestamp sat inside the
hashed body, so the same corpus produced a different hash every run, making the
reproducibility claim meaningless. The timestamp is now set *after* hashing.

**DEFECT 5 — no integrity check existed.** Every verdict cites the rulepack hash, but
nothing verified it. A silent edit would have forged the legal basis of past findings.
`load()` now recomputes and refuses on mismatch.

### C. The comparison

| Attack | Outcome |
|---|---|
| 21 scenarios: measurement, evidence, format, exemptions, e-commerce | 21/21 |
| OCR noise 0 → 40% on compliant labels | 0% false accusations |
| Genuine violations under the same noise | 0 missed; 77–100% caught to 10% error |
| All five Table-I bands (30 / 75 / 215 / 1200 / 4000 cm²) | All exercised, correct threshold each |
| All four interior boundaries (50 / 100 / 500 / 2500 cm²) | All abstain — `<` vs `≤` unresolved |
| **Inspect the same package on different dates** | **DEFECT 6** |
| Operator that does not exist | SYSTEM_ERROR, never a violation |

**DEFECT 6 — the engine ignored effective dates entirely.** The rulepack carried
`effective_from` on every check and nothing read it. A package inspected in 2016 would
have been judged by 2018 law, and re-running an old scan after an amendment would have
rewritten its verdict. Both are legally void.

*Now:* scans carry a capture date, checks are filtered by the law in force on that day,
and Table-I keeps its **repealed** net-quantity version so old findings stay reproducible.

```
A 2.2 mm label on a 500 g pack, 215 cm² panel — the same package:
  31 Dec 2017   PASS   2.20 mm against 2.0 mm required by the table then in force
                       (keyed to net quantity)
  01 Jan 2018   FAIL   2.20 mm against a required 2.5 mm for a 215 cm² panel
```

**Defects 7–12** were found in the earlier engine stress run and are documented in
`END-TO-END-STRESS-TEST.md`: a verdict ceiling suppressing all font violations; absence
concluded from an unreadable image (60% of compliant labels accused at 5% error); format
checks failing on OCR damage; a repair corrupting neighbouring words; a confusion mapping
doing net harm; legal wording matched exactly instead of fuzzily; and a partial parse
passing an unrounded price as rounded.

---

## 2. The principles the campaign produced

Three rules that were not in any design document and that the testing forced:

1. **Identity is (number, year), never the number.** Any government citation scheme that
   restarts annually will collide within a decade.
2. **Different claims need different confidence.** *"There is text here"* survives a
   misread glyph (0.80). *"This character is wrong, therefore the form is violated"* turns
   on one glyph (0.95). *"Thirty characters of required wording are absent"* is robust
   again (0.80). One threshold for all three produced either false accusations or silent
   misses, depending where it was set.
3. **Repealed law must be retained, not deleted.** A finding is only reproducible if the
   version that governed it still exists inside the rulepack.

---

## 3. What is now proven

- The law can be fetched, classified, ordered and compiled **automatically**, from the
  real government site, current to an instrument published four months ago.
- The compiler **generalises** — 94% on two rule families it was never developed against.
- The build **refuses to ship** when it cannot prove the pack is current, correct and
  intact. Seven distinct refusal paths are tested.
- Verdicts are **reproducible, hash-addressed, and dated** — the same corpus gives the
  same rulepack, and an old scan keeps the law that governed it.
- Under degrading input the system **stops answering rather than guessing**, with a
  measured operating envelope (confident to ~10% character error, abstains beyond).

---

## 4. What is NOT proven — read this before approving

1. **Real OCR has never been run.** PaddleOCR is not installed here. Token geometry is
   exact by construction; a real recogniser also mis-segments lines and merges blocks,
   which nothing here models. *This is the largest untested gap.*
2. **No real photograph has been processed.** No perspective, glare, curvature, shadow or
   motion blur. Every label is a flat render.
3. **Devanagari is in the lexicon but never exercised end to end.** No Hindi label has
   been through the pipeline.
4. **The base 2011 rules are not in the corpus** — they are a scanned bilingual PDF.
   Twelve of the twenty bindings therefore trace to no corpus amendment, and the build
   warns about exactly that.
5. **The `<` vs `≤` question is still legally open.** Everything within 0.5 cm² of a
   Table-I boundary abstains. That is safe, not solved.
6. **Only the Packaged Commodities family is bound to checks.** General Rules and GATC are
   parsed and chained but nothing is compiled from them.
7. **No concurrency, scale or long-run testing.** Single process, single machine.
8. **The sensitivity sweep drives two violation types**, not all seventeen checks.

---

## 5. Conditions for approving the engineering plan

1. **Week 1 gains an OCR reality check.** Run PaddleOCR against 20 real package
   photographs before any further engine work, and re-measure the false-accusation rate.
   Everything in §4.1–4.3 is unvalidated until this happens.
2. **OCR the eight 2011–2015 scans** so the base rules enter the corpus and the twelve
   unverified bindings close.
3. **Every rule family the system claims to cover must have its own bound checks** — or
   the claim is dropped from the scope statement.
4. **The `<` vs `≤` ruling gets a named owner and a date.** Until then the guard band
   stays and is disclosed on reports.
5. **The campaign runs in CI on every change**, and the plan's acceptance gate becomes
   "campaign green", not a subjective review.

With those five, the rulepack architecture is sound enough to build on. Without the
first one, the measured numbers in this report describe a simulator, not a system.
