# Wider Real-World Test — More Products, More Rules, Harder Tests

**What we did:** took a second, different set of real product photos — this time
cosmetics, household goods and pet food, not just packaged food — added four more real
rules from the law, and tested everything again more strictly.

**Run it:** `python -m stress.realworld food` · `python -m stress.realworld wide` ·
`python -m stress.campaign` · `pytest -q`

---

## What changed since last time

| | Before | Now |
|---|---|---|
| Real products tested | 60 (food only) | **140** (food, cosmetics, household, pet food) |
| Real photographs | 211 | **394** |
| Rules checked | 17 | **21** |
| "Does this law apply?" gates | 3 | **4** |
| Test scenarios | 21 | **28** |
| Automated tests | 44 | **45** |

**The new data:** 43 cosmetics (Vaseline, Dettol, Cetaphil, Sensodyne), 22 household
goods (Navneet notebooks, cleaning products), 12 pet foods, and 3 products the system
flagged as medicines (Vicks, Eno and similar).

**The new rules**, each taken from the actual gazette text:

| Rule | What it says | Why it is interesting |
|---|---|---|
| Rule 9(4) | Declarations must be in Hindi (Devanagari) or English | Other languages are allowed *in addition* — so a third language is never a violation on its own |
| Rule 6(3) | No stickers changing declarations, except a **lower** MRP sticker that doesn't cover the original | Two prices on one pack is legal in one specific case, so we flag for review rather than accuse |
| Rule 6(1)(d) | Packing date | A date in the future is a misprint or a misread — never an automatic finding |
| Rule 10(1) | Packets of 10 cm³ or less need only an identifying mark | The 2017 amendment raised this from 5 cm³ |
| Rule 26(c) | Medicines under the Drug Price Control Order are **completely outside** these rules | First category exemption to fire on real products |

---

## Every scenario tested, and the result

### Different kinds of product

| Scenario | Result |
|---|---|
| Cosmetics judged by the same rules as food | Correct — no food-specific rule leaked in |
| **Medicines (Vicks, Eno)** | **Correctly ruled outside the law entirely.** 3 of 3 |
| Household goods (notebooks, cleaners) | Handled normally, 1 real violation found |
| Pet food | Handled normally |
| Imported products | Country-of-origin rule triggered on 4 |

### Different photo conditions

| Scenario | Result |
|---|---|
| 64-megapixel phone photos | **Crashed the system.** Now fixed |
| Very dense small print (ingredients panels) | Took minutes on CPU; **2.3 seconds on GPU** |
| Only part of the packet photographed | Refused to accuse — correct |
| Photos from a public database (not our own capture) | **Now always refuses to accuse.** See below |

### New rules

| Scenario | Result |
|---|---|
| A label written only in Hindi | **Passed** — Hindi is legal on its own |
| English plus Tamil | Passed — extra languages are allowed |
| Two different prices on one pack | Flagged for review, not accused |
| A single price | Not flagged |
| Packing date in the year 2030 | Flagged for review |
| An 8 cm³ sachet | Correctly given the small-package relaxation |
| A medicine | Correctly ruled out of scope |

---

## The three problems this round found

### Problem 1 — the system crashed on real phone photos

Modern phone cameras produce enormous files. Some photos here were **9248 × 6936 pixels —
64 megapixels**. Handing one of those to the text reader used all the memory and never
finished. The run looked frozen.

**Why we missed it twice:** two earlier attempts to fix this silently did nothing. The
edit looked for a line of code that had already changed, didn't find it, and made no
change without complaining. **We now check that every edit actually applied.**

**The fix:** shrink every photo to 1800 pixels on its longest side before reading it. A
dense 50-megapixel ingredients panel went from *never finishing* to **2.3 seconds**.

### Problem 2 — we were treating a database label as proof of what was photographed

The photo database calls one image "ingredients" because it shows the ingredients list. We
were reading that as *"the back of the packet has been photographed"*. It has not — it is
a close-up of one corner.

So when the price wasn't visible, the system concluded **"the price is missing"** and
issued a violation. On Dettol 550 ml it accused the product of missing three separate
declarations that are almost certainly printed on a side nobody photographed.

**The fix — and it is an important one.** The system now needs the capture app to
*explicitly confirm* that every side was photographed. Without that confirmation, "we
didn't find it" can never become "it isn't there".

This turns the guided-capture requirement from a nice idea in the plan into something the
code actually enforces.

### Problem 3 — we were measuring the wrong thing, carefully

Rule 7(3) says a letter must be at least one-third as wide as it is tall. We were
measuring the average letter width against the **height of the box the text reader drew** —
and that box includes the tall bits of letters like "h", the tails of "g", and blank
padding.

So the height was always too big, so the ratio was always too small, so the system
accused **11 products** of thin lettering at believable-looking numbers like 0.151.

Last round this check produced obviously-broken values (0.001) and we filtered those out.
This round it produced *plausible* wrong values, which is worse — nobody would have
questioned them.

**The fix:** this check now refuses to answer unless it can measure individual letters.
That needs extra work nobody had planned for, and it is better to know now.

---

## Results across all 140 real products

| Measure | Result |
|---|---|
| Products tested | 140 |
| Photographs | 394 |
| Individual checks run | **2,940** |
| Said "cannot determine" | 1,182 (40%) |
| Said "rule does not apply" | 1,624 (55%) |
| Passed | 129 |
| **Found a violation** | **3** |
| **False accusations** | **0** |
| Violations before this round's fixes | 21 |

**The 3 violations found** — all the same rule, all plausible, all needing an officer to
confirm:

| Product | Finding |
|---|---|
| Marie Gold biscuits | Weight printed 1 pixel from other text; the rule needs 21 |
| Sensodyne toothpaste | Weight has 18 pixels of clear space; needs 33 |
| Navneet notebook | Weight has 3 pixels of space on the side; needs 72 |

---

## How much resolution does reading small print need?

We measured this instead of guessing. Ten products, four settings:

| Photo size | Seconds per photo | Text pieces found | MRPs found |
|---|---|---|---|
| 800 px | 0.8 | 452 | 1 of 10 |
| 1280 px | 0.9 | 514 | 1 of 10 |
| 1800 px | 1.6 | 528 | 2 of 10 |
| 2400 px | 2.3 | 558 | **3 of 10** |

**What this tells us:** bigger photos read better, and cost roughly proportional time.
There is no free lunch and no obvious sweet spot — even at the largest size we only find
3 MRPs in 10. Resolution is not the main problem.

---

## The honest summary

**The safety design is holding up very well.** Across 2,940 checks on products it had
never seen, in categories it was never tuned for, it made **zero false accusations**. Each
round of real data has found ways it could accuse someone wrongly, and each has been
closed.

**The reading is still the weak part.** We find the MRP on roughly 1 product in 10 overall.
Most of that is because the price simply isn't in the photograph — but not all of it.

**Category rules work.** Medicines were correctly ruled out of scope on real products. That
was the single biggest legal risk — accusing a product that the law does not govern — and
it behaved correctly.

**Hindi is still untested on real labels.** Every photo in both sets shows an
English-facing side. The Hindi rule passes on rendered labels, but no real Devanagari
packet has been through the system.

### What this changes in the plan

1. **Guided capture is now a hard requirement, not a preference.** The code refuses to
   issue a violation without it. This is the single most valuable change of the round.
2. **Rule 7(3) needs letter-level measurement.** It was listed as "build this first, it
   needs no calibration". That was wrong. Add the work or drop the check.
3. **Set a resolution budget of 1800–2400 px** and a GPU on the server. On a CPU, a dense
   ingredients panel alone blows the 30-second promise.
4. **Find Hindi labels and test them.** This is the largest untested area remaining.
5. **Keep every check gated on a trustworthy measurement.** Three rounds, three cases of a
   check answering confidently from a measurement it should not have trusted. Assume the
   fourth exists.

---

> ### Correction — 2026-09-08
>
> This report is kept as the dated record of what was found on the day. Two of its
> conclusions were later shown to be wrong, and are corrected here rather than edited
> above.
>
> **1. Hindi was not "untested" — it was impossible.** The report attributes the absence of
> Devanagari to the photographs showing English-facing panels. The real cause is that the
> shipped recogniser is the **Chinese** PP-OCRv3 model, whose 6,625-character set contains
> **zero Devanagari characters**. Rendered Hindi returns `00000.00000 2`. Fixed by shipping
> specialist English and Devanagari recognisers — see `02-BUILD-SPEC.md` M.19 and
> `07-WHAT-RUNS-WHERE.md` §6.
>
> **2. The timings recorded as GPU were CPU.** `onnxruntime` advertises
> `CUDAExecutionProvider` even with no CUDA runtime installed and falls back to CPU with a
> warning that was being swallowed. Every figure in this report is a CPU figure — which is
> good news: CPU is fast enough, and a GPU is optional. See M.18.

> ### Correction — 2026-09-10
>
> The wide dataset's artifacts were missing from the repository, so its numbers above were
> not reproducible from the repo. The dataset has been **regenerated** with the same public
> harvester (`python -m stress.realworld wide`) and committed. The regenerated set differs
> in composition, so the headline numbers change:
>
> | | As reported above | Regenerated 2026-09-10 |
> |---|---|---|
> | Products (wide) | 80 | **80** |
> | Photographs (wide) | 183 | **192** (54 cosmetic, 20 general, 6 pet food) |
> | All products / photographs | 140 / 394 | **140 / 403** |
> | Rule evaluations | 2,940 | **2,700** |
>
> What is unchanged and re-confirmed by the regeneration: the safety metric — **0 FAIL
> verdicts issued for a declaration on an unphotographed panel** — and Devanagari still
> absent from the photographs (0/80), so the Hindi gap (M.19) remains the largest untested
> area. The 17 FAIL verdicts the fresh run issued are findings, not reviewed conclusions;
> the "zero false accusations" figure above rests on the reviewed runs recorded in this
> report and in REAL-WORLD-TEST.md.
