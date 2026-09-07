# Prototype Test — Compiling the Law Instead of Retyping It

**Run:** 2026-09-07, against the live corpus at
`https://consumeraffairs.gov.in/pages/legal-metrology-act`
**Claim under test:** an amendment gazette can be turned into rulepack changes
automatically, so a human approves a **diff** rather than hand-writing YAML.
**Reproduce:** `./run.sh`  (needs `curl`, poppler's `pdftotext`, `python3` — no pip installs)

---

## Result

| Measure | Result |
|---|---|
| PCR documents fetched from the live site | **30** |
| Machine-readable without OCR | **22 of 30** (all 2016→2026 instruments) |
| Needing OCR | 8 — every one of them from **2011–2015** |
| Amendment chain reconstructed | **12 links**, G.S.R. 418(E) *(29 May 2026)* → G.S.R. 60(E) *(27 Jan 2023)* |
| Patch operations parsed | **56** |
| Table-I values lifted automatically | **5 rows, correct**, every boundary self-flagged |
| Human input required for the 2017 Table-I change | **confirm 5 boundary operators** — no retyping |

---

## What it did

### 1. The chain reconstructs itself, and reports what is missing

Every notification ends with *"…was last amended vide number G.S.R. X, dated …"*. Walking
those pointers backwards from the newest instrument gives an ordering with no human input:

```
G.S.R. 418(E) → 312(E) → 128(E) → 881(E) → 778(E) → 722(E)
              → 714(E) → 640(E) → 463(E) → 412(E) → 214(E) → 60(E)
              → G.S.R. 910(E), 29 December 2022   ← NOT PUBLISHED ON THE DoCA PAGE
```

The walk stops and names the gap. **G.S.R. 910(E) is referenced by G.S.R. 60(E) but does
not appear anywhere in the 93 PDF links on the government page.** The department's own
listing is incomplete, and the tool proves it in one run rather than someone noticing.

This is the honest answer to *"how do you know your rules are current?"* — not a claim, a
reachability check.

### 2. Amendment prose parses into typed operations

56 operations across the corpus, addressed to stable node IDs. From the 2017 amendment:

```
substitute   lmpc/r7/sr2        <- sub-rule (2)
substitute   lmpc/r7/sr3        <- sub-rule (3)
substitute   lmpc/r7/table-I    <- the Table-I
omit         lmpc/r7/table-II   <- Table II
```

Those four lines are the entire reason our flagship check works. Nobody read 14 pages.

### 3. Table values reload without being retyped

A binding attaches to `lmpc/r7/table-I`, **not to the numbers in it**. When the amendment
substitutes that node, the parameters reload:

```
lmpc/r7/table-I  substitute -> LMPC-R7-2-MIN-HEIGHT
  RELOAD parameters — no code change, no retyping

  was: keyed_by net_quantity        now: keyed_by pdp_area_cm2
       up to 200 g/ml    1.0 mm          A < 50          1.0 mm  (molded 1.5)
       200 g/ml – 1 kg   2.0 mm          50 < A < 100    1.5 mm  (molded 3.0)
       above 1 kg        4.0 mm          100 < A < 500   2.5 mm  (molded 4.0)
                                         500 < A < 2500  4.0 mm  (molded 6.0)
                                         2500 < A        6.0 mm  (molded 6.0)

  human action: confirm 5 boundary operators
lmpc/r7/table-II omit -> REPEAL check — stop evaluating it
```

Extracted values match `docs/02-ENGINEERING-SPEC.md` §II.1 exactly — which was compiled by
hand from the page images. **The automated path and the manual path agree.**

### 4. It refuses to trust its own boundary reading

Every one of the 5 rows came back `needs_human_confirmation: true`. The 2017 gazette's
embedded font drops the `≤` glyph, so `pdftotext` renders `A ≤ 50` as `A < 50`. Boundary
operators are exactly the values that get litigated, so the compiler flags every one for
confirmation against the page image instead of silently shipping `<`.

**This is the safety property that makes automation acceptable here.** A system that
extracted these confidently would be wrong at four thresholds and never say so.

---

## What broke — real corpus, real defects

| Found | Handling |
|---|---|
| `G.S.R. . 778(E)` — stray period, a typo in the actual gazette | Regex tolerates punctuation between `G.S.R.` and the number |
| `"30 th August, 2023"` — `pdftotext` splits the ordinal | Date pattern allows the space |
| `"Rules, 2022were published"` — missing space in the source | Matched anyway |
| First amendment to an instrument has **no** "last amended" clause | Optional; flagged `is_first_amendment_of_parent` |
| 2011–2015 gazettes are **two-column scans**; the Note interleaves with body text | Classified `SCANNED_NEEDS_OCR`, excluded from the chain rather than mis-parsed |
| The "last amended" chain and the "which instrument does this amend" declaration are **different graphs** — G.S.R. 722(E) amends the principal rules but points back to 714(E), which amends the 2022 Amendment Rules | Chain walks all instruments; parent kind is metadata, not a filter |

---

## Honest limits

1. **Node IDs are incomplete.** Some operations resolve to `lmpc/?` because the rule
   context sits in a preceding sentence the splitter didn't carry. Fixable with a proper
   sectioniser; today roughly a third of operations need the rule number supplied.
2. **Only 4 bindings are seeded.** Getting to the full ~17 checks is a day's work in
   Week 1 — but it is **one-time**, which is the whole argument. Recurring cost per
   amendment is approving a diff.
3. **Operations are proposed, not applied.** Nothing writes to a live rulepack. Producing
   a full consolidated text needs the 8 scanned 2011–2015 documents OCR'd first.
4. **Text-layer extraction is not sufficient on its own** — see the `≤` problem. The
   production version must crop the table region from the page image and put it beside the
   parsed values in the approval screen.
5. Regexes are tuned on 30 documents from one rule-set. Other Legal Metrology rule
   families will surface variants this does not yet handle.

---

## What this changes in the plan

The Week 1 deliverable is no longer *"two people read the law and type YAML."* It is
*"seed ~17 bindings, then approve compiler output."* The chain check becomes a standing
alert: when a new notification appears, the walk either extends cleanly or names exactly
what is missing.

Files: `lawc.py` (compiler, ~200 lines) · `bind.py` (binding + diff) · `run.sh` (fetch and
run) · `compiled.json`, `rulepack-diff.json` (outputs).
