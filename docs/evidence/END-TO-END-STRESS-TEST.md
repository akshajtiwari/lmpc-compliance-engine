# End-to-End Stress Test — Rulepack to Verdict

**Run:** 2026-09-07 · `python -m stress.run` · `pytest -q`
**Question under test:** *what are we comparing against, and is it accurate, current, and
testable?*

---

## Result

| | |
|---|---|
| Rulepack | `lmpc-2026-09-07` · sha256-addressed · 3 gates, 17 checks |
| Current to | **G.S.R. 418(E), 29 May 2026** — via 12 verified chain links |
| Scenario expectations | **21 of 21 met** |
| False accusations on compliant labels | **0%** at every noise level 0 → 40% |
| Violations silently passed as compliant | **0** |
| Tests | **20 passed** |

The system answers confidently up to roughly **10% character error**, then stops
answering rather than guessing. That envelope is the deliverable, not a limitation to
hide.

---

## How the test avoids grading its own homework

Real package photographs have no ground truth: nobody knows to a tenth of a millimetre
how tall the MRP glyphs are, so any verdict about a 2.5 mm threshold is unfalsifiable.

Instead labels are **rendered** at 300 DPI with a chosen panel size in centimetres and a
chosen cap height in millimetres, then the renderer **measures what it actually drew**.
The expected verdict is therefore derived from physics, not asserted by the author. OCR is
simulated on that exact geometry with realistic damage — `0`/`O`, `1`/`l`, `5`/`S`
confusions, dropped separators, random substitutions, degraded confidence.

---

## What the 21 scenarios cover

| Group | Scenario | Required verdict |
|---|---|---|
| Measurement | 2.8 mm on a 215 cm² panel | PASS |
| | 1.6 mm on a 215 cm² panel | FAIL |
| | 2.5 mm measured against a 2.5 mm threshold | INDETERMINATE |
| | panel area exactly 500 cm² | INDETERMINATE |
| | moulded container at 3.0 mm (needs 4.0) | FAIL |
| Evidence | no scale reference in frame | INDETERMINATE |
| | back panel never photographed | INDETERMINATE |
| Format | MRP without "inclusive of all taxes" | FAIL |
| | MRP Rs. 45.30 (not rounded) | FAIL |
| | quantity crowded by other print | FAIL |
| Applicability | 8 g sachet | NOT_APPLICABLE |
| | 8 g **tobacco** sachet | FAIL — the proviso removes the exemption |
| | 30 kg bulk pack | NOT_APPLICABLE |
| | institutional buyer | NOT_APPLICABLE |
| | e-commerce listing | packing date NOT_APPLICABLE, MRP still PASS |

---

## What the stress test found — seven real defects

Every one of these was a working system producing a wrong legal conclusion. None was
visible from reading the code.

**1. A verdict ceiling applied to every FAIL, not just the ones it was meant for.**
`INDETERMINATE_NEAR_BOUNDARY` was written for Table-I boundary ambiguity but suppressed
*all* font-size violations. A 1.6 mm label came back "undetermined". Ceilings now name
what they cap.

**2. Absence was concluded from an unreadable image.** At 5% character error, **60% of
compliant labels were accused.** The presence check reasoned "both panels photographed,
declaration not found, therefore missing" — when the truth was that the image could not be
read. Absence now requires *legible* evidence, and a near-miss candidate forces
INDETERMINATE.

**3. Format checks failed on OCR damage rather than on labels.** `MRP Rs. 4S.00` is a
compliant label misread. Known confusions are now repaired inside numeric runs only, and a
match that appears only after repair yields INDETERMINATE — the *reading* is in doubt, not
the label.

**4. The repair itself corrupted neighbouring words.** Translating globally turned `Rs.`
into `R5.` and `incl.` into `inc1.`, so the repair re-broke what it was meant to fix.
Repair is now scoped to character runs that already contain a real digit.

**5. A confusion mapping did more damage than good.** `G`→`6` turned `MFG02/2025` into
`MF 602/2025`, converting a compliant date into a violation. Removed. *A repair that can
damage a neighbouring word is worse than no repair.*

**6. Prescribed legal wording was matched exactly when it should have been matched
fuzzily.** `incl. of all taxes` read as `incl. of gll taxes` failed a compliant label.
Wording is now fuzzy; digits stay exact. **The digits are the finding; the words are the
context.**

**7. A partial parse passed an unrounded price as rounded.** `45.b0` parsed as `45.0` —
the paise were silently dropped and a violation read as compliant. This was the only
*missed* violation in the run, and the most dangerous class of bug. The parser must now
consume the numeral end to end or return INDETERMINATE.

---

## The principle the run produced

Fixing #2, #6 and #7 forced a distinction that was not in any design document:

> **Different claims need different confidence.**
>
> *"There is text here"* survives a misread character — it needs only legibility (0.80).
> *"This character is wrong, therefore the form is violated"* is decided by a single glyph
> — it needs 0.95.
> *"Thirty characters of required wording are simply absent"* is robust again — 0.80.

Applying one threshold to all three produced either false accusations or silent misses,
depending on where it was set. Three thresholds, matched to what is being claimed, gave
0% false accusations **and** 0 missed violations at the same time.

---

## Detection versus abstention

Withholding accusations is only worth anything if genuine violations are still caught. The
counter-metric:

| Character error | Violations caught | Abstained | **Missed** |
|---|---|---|---|
| 0% | 100% | 0% | **0** |
| 2% | 93–100% | 0–7% | **0** |
| 5% | 92–98% | 2–8% | **0** |
| 10% | 77–95% | 5–23% | **0** |
| ≥15% | 0% | 100% | **0** |

The cliff at 15% is deliberate: confidence drops below the legibility floor and the system
stops issuing findings entirely. It never crosses into guessing.

---

## The rulepack side

- Built from **30 gazette PDFs fetched live**; 22 machine-readable, 8 (2011–2015) need OCR.
- Table-I values are lifted from G.S.R. 629(E) automatically and **cross-checked against
  what a reviewer confirmed**. A mismatch fails the build — tested.
- All five boundary rows are flagged `boundary_confirmed_by_human: false`, because the text
  layer drops `≤`. The check therefore abstains within 0.5 cm² of any boundary.
- The build **refuses to emit a rulepack** when the amendment chain has an unexplained
  hole. G.S.R. 910(E) (29 Dec 2022) is genuinely unpublished on the DoCA site; it is
  recorded in `gaps.yaml` with the searches performed, an impact assessment, and a named
  reviewer — and the disclosure is printed on **every report**.

---

## Honest limits

1. OCR is simulated. Token geometry is exact by construction; a real recogniser will also
   mis-segment lines and merge blocks, which this does not model.
2. Labels are flat renders. No perspective, glare, curvature or motion blur.
3. Twelve of the 20 bindings trace to the base 2011 rules rather than to an amendment in
   the corpus — the build warns about this. Closing it needs the base PDF OCR'd.
4. Two violation types drive the sensitivity sweep. It should cover all 17 checks.
5. The `<` vs `≤` question is still open. Everything near a boundary abstains until a
   legal reviewer rules.
