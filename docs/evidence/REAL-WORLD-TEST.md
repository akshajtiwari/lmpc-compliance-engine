# Real-World Test — Real Photos, Real OCR, Real Law

**What we did:** downloaded photographs of 60 real Indian packaged products, read them
with a real OCR engine, and ran them through our rule system.

Nothing here is made up. The photos are of actual packets sold in shops — Parle-G, Tata
Salt, Kurkure, Balaji wafers, Frooti, Sprite — taken by ordinary people on ordinary
phones. The law is the real law, current to 29 May 2026.

**Where the photos came from:** Open Food Facts, a free public database of product
photos. 60 products, 211 photographs, 3 to 4 sides each.

**Run it yourself:** `python -m stress.realworld`

---

## The short version

**Good news:** the system never made a false accusation. Not once in 1,020 checks.

**Bad news:** it also could not read most of the labels. It found the MRP on 6 products
out of 60.

**The honest reason:** on 48 of those 60 products, the MRP was never photographed. People
photograph the front of a packet and the ingredients list. They do not photograph the
small print. Of the 12 packets where the price and weight are actually visible in the
photo, we found the MRP on **6 of 12**.

So the real number is roughly **half**, not one in ten — and half is still not good enough
to ship.

---

## Every scenario we tested, and what happened

| # | Scenario | What happened | Verdict |
|---|---|---|---|
| 1 | 60 real product photos through real OCR | 3,433 pieces of text read | Works |
| 2 | Front-of-pack photo only (most common case) | System said "cannot tell", never "missing" | **Correct** |
| 3 | Price and weight actually visible in photo | Found the MRP on 6 of 12 | Weak |
| 4 | Weight checked against the product record | Matched exactly 1 time in 9 | **Poor** |
| 5 | No ruler or reference card in any photo | Font-size checks refused to answer | **Correct** |
| 6 | OCR splits "NET WEIGHT :" from "220" | Broke the system completely at first | **Fixed** |
| 7 | OCR removes spaces: "MRPRS.10/-" | Broke the system at first | **Fixed** |
| 8 | Letter-width check on a real photo | Gave nonsense (0.001) and called it a violation | **Fixed** |
| 9 | Spacing check on a real photo | Gave negative distance and called it crowding | **Fixed** |
| 10 | Width check measured "A QUALITY PRODUCT OF" | Accused marketing text of breaking a rule | **Fixed** |
| 11 | Packets under 10 g in the set | Correctly treated as outside the law | Correct |
| 12 | Hindi text on labels | None found — these photos show English sides | Untested |
| 13 | Accusations on a side never photographed | **Zero** | **Correct** |

---

## What went wrong, in plain words

### Problem 1 — the biggest one. The label is not one piece of text.

We assumed a label says `MRP Rs. 45.00 (incl. of all taxes)` in one go.

Real OCR reads it as three separate pieces, sometimes far apart on the packet:

```
"NET WEIGHT :"            "220"            (two separate readings)
"MRP"                     "Rs.10.00"       (two separate readings)
```

Our system looked at each piece on its own, saw no complete declaration anywhere, and
found nothing. **It found 0 MRPs out of 60.**

**The fix:** before judging anything, glue together pieces of text that sit on the same
line of the packet. It is just geometry — things printed side by side belong together.
After this, we found 6 of 12. Still not enough, but 6 is not 0.

### Problem 2 — OCR deletes spaces.

Real readings from the actual photos:

```
"MRPRS.10/-(INCL.OFALLTAXES)"
"BATCHNO.MEDMRPINCLUSHEOFALLTAXEST:SEENECK"
"NutritionalInformation"
```

**The fix:** put spaces back where a letter meets a digit, then try again. We had already
guessed this problem existed during simulated testing. Real photos confirmed it is worse
than we guessed.

### Problem 3 — two checks accused innocent packets.

These are the important ones, because they are *wrong answers*, not missing answers.

**The letter-width check** measured a ratio of `0.001` and called it a violation. That
number is impossible for real printing. It happened because we measured a box that
covered two lines of text at once, so the "letter height" was double what it should be.

**The spacing check** reported `-122 pixels` of clear space around the weight. Negative
space does not exist. Two text boxes overlapped, and the system read that as crowding.

**The fix:** both checks now refuse to answer unless the measurement is physically
possible and comes from a single clean reading. **False accusations dropped from 19 to 2.**

### Problem 4 — we accused marketing text of breaking the law.

On the Sprite bottle, the width check measured the words **"A QUALITY PRODUCT OF"** and
issued a violation. That is advertising copy. The rule only covers legally required
declarations.

**The fix:** only measure the declarations the law actually names.

---

## What the system got right

**It never accused a packet based on a side it had not seen.** Zero times out of 60. When
the price was not in the photo, it said *"cannot determine"* — not *"the price is
missing"*. This is the single most important safety property, and real photos confirmed
it holds.

**It refused every millimetre measurement.** None of these photos has a ruler or a bank
card in frame for scale. Without that you cannot tell 2 mm from 4 mm in a photograph. The
system said so, 59 times out of 60, instead of guessing.

**Two remaining violations look genuine.** Marie Gold biscuits and Kurkure both show the
weight printed too close to other text (Rule 8 needs clear space around it). These need an
officer to confirm, but they are the right kind of finding.

---

## What this means for the plan

**The architecture survived contact with reality.** The safety design — refuse rather than
guess — worked exactly as intended on data it had never seen. That is the part that was
hardest to get right and it held.

**The reading layer is not ready.** Finding the MRP on half of clearly-photographed labels
is not good enough for enforcement. This is a solvable engineering problem, not a design
flaw, and it now has a measured starting point instead of an assumption.

**Photographing the packet correctly matters more than any algorithm.** 48 of 60 failures
were "the price was not in the picture." No amount of software fixes that. The guided
capture flow — telling the officer *"now photograph the side with the price"* and refusing
to proceed until they do — is worth more than a better OCR model.

### What to change in the plan

1. **Guided capture moves to Week 2 and gets first priority.** It is the largest single
   cause of failure in this test.
2. **Add a "scale reference" step to capture.** A bank card in frame is free and turns
   every font-size check from "cannot tell" into a real answer.
3. **Budget real work for the reading layer.** The target is finding the declaration on
   90% of correctly photographed packets. We are at 50%.
4. **Test Hindi separately.** These photos happened to show English sides. Nothing about
   Devanagari has been tested end to end.
5. **Keep every check gated on trustworthy measurement.** Four of the five bugs found here
   were checks that answered confidently from bad measurements. That pattern will repeat.

---

## The numbers

| Measure | Result |
|---|---|
| Products / photographs | 60 / 211 |
| Pieces of text read by OCR | 3,433 |
| Products where a declaration is legible in the photo | 12 of 60 |
| MRP found (of those 12) | 6 — **50%** |
| Weight found (of those 12) | 5 — **42%** |
| Weight matching the product record exactly | 1 of 9 — **11%** |
| Total checks run | 1,020 |
| "Cannot determine" | 46% |
| "Rule does not apply" | 51% |
| Passed | 3% |
| **Failed (accusations)** | **2** |
| **False accusations on unseen panels** | **0** |
| Bugs found and fixed by this test | **5** |

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
