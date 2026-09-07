# The Rulepack — Structure, Architecture, Flow

The rulepack is the app's copy of the law. This document is only about that: what it is,
what is inside it, how it gets made, and how it stays current.

Ten minutes. Implementation detail is in `02-BUILD-SPEC.md` Part A.

---

## 1. What it is

A **single file of a few kilobytes** containing every number and pattern the app needs to
judge a label — plus a fingerprint proving it has not been altered.

```
rulepack/current.json     21 checks · 4 gates · ~40 KB · sha256-addressed
```

It is **generated**, never hand-edited. It is the *only* thing the running app knows about
the law. No gazette PDF, no website, no search happens during a scan.

---

## 2. What is inside

Four sections.

### (a) Currency — "how do we know this is up to date?"

```json
"currency": {
  "newest_instrument": "G.S.R. 418(E)",     // 29 May 2026
  "chain_links_verified": 12,               // walked back through 12 notifications
  "chain_complete": false,
  "acknowledged_gaps": [
    { "gsr": "G.S.R. 910(E)", "reviewer": "akshaj.tiwari",
      "text": "not published on the DoCA website; assessed as affecting nothing we check" }
  ]
}
```

This is what answers *"is this current law?"* — with a chain of evidence, not a claim.
Any gap travels inside the pack and prints on **every report**.

### (b) Gates — "does this law apply at all?"

Four of them. They run **before** any check. If one fires, evaluation stops.

```json
{ "id": "GATE-R26-EXEMPT", "clause": "Rule 26",
  "params": { "any_of": [
      { "field": "net_quantity_g", "lte": 10,
        "unless_field": "category", "unless_in": ["TOBACCO"] }, … ] },
  "effect": "ALL_RULES_NOT_APPLICABLE" }
```

*A 10 g sachet is outside these rules entirely — unless it is tobacco.*

### (c) Checks — the 21 actual rules

```json
{ "check": "LMPC-R7-2-MIN-HEIGHT",
  "node": "lmpc/r7/table-I",              ← the ADDRESS in the law (see §5)
  "clause": "Rule 7(2) Table-I",
  "operator": "table_lookup",             ← which of the 12 checkers runs
  "effective_from": "2011-04-01",         ← when this requirement began
  "citation": { "gsr": "G.S.R. 629(E)", "page": 11 },
  "params": {
    "input": "pdp_area_cm2",
    "versions": [                         ← the law, dated (see §6)
      { "effective_from": "2011-04-01", "effective_to": "2017-12-31",
        "keyed_by": "net_quantity_g",  "rows": [ … repealed … ] },
      { "effective_from": "2018-01-01", "effective_to": null,
        "keyed_by": "pdp_area_cm2",
        "rows": [ { "upper_cm2": 500, "min_mm": 2.5, "molded_mm": 4.0,
                    "boundary_confirmed_by_human": false }, … ] }
    ]
  },
  "verdict_ceiling": "INDETERMINATE_NEAR_BOUNDARY" }
```

Every check carries: **which rule**, **which operator**, **which numbers**, **which
gazette page**, **which dates**, and **what it is not allowed to conclude**.

### (d) Modes

```json
"modes": { "ECOMMERCE_LISTING": { "excludes": ["LMPC-R6-1-D-MFG-DATE", …] } }
```

*Rule 6(10): an online listing needs every declaration except the packing date.*

---

## 3. How it is made the first time

Six steps. Only step 5 is human, and it happens once.

```
1  FETCH      download the gazette notifications                       automatic
2  READ       text out of the PDFs; scans flagged for OCR              automatic
3  ORDER      each says "last amended by X" → walk the chain backwards automatic
4  PARSE      "rule 7, Table-I, shall be substituted" → an operation   automatic
              pull the new numbers straight out of the table
5  BIND       point each rule at one of 12 checkers, and record        ← HUMAN
              what a reviewer confirmed against the page image           (one day)
6  BUILD      assemble, cross-check, hash                              automatic
```

**Step 5 is smaller than it sounds.** There are only twelve checkers, written once as
ordinary code:

| Kind | Example |
|---|---|
| is it present? | is there an MRP at all? |
| is it written correctly? | does it say "inclusive of all taxes"? |
| is a number big enough? | letter width vs height |
| look it up in a table | font size for this panel size |
| do two values agree? | unit price vs MRP ÷ weight |
| does this rule apply? | is the pack over 25 kg? |

Everything else — the numbers, the patterns, the tables — is lifted out of the gazette
automatically. A person points and confirms; they do not transcribe.

---

## 4. How it stays current

```
new notification published
        ↓
watcher finds it  →  QUARANTINE          nothing is live yet
        ↓
compiler          →  identify · check the chain · parse the change · read the table
        ↓
        ┌──────────────────────────────────────────────────┐
        │  rule 7, Table-I  — REPLACED by G.S.R. 418(E)    │
        │    before   100–500 cm² → 2.5 mm                 │
        │    after    100–500 cm² → 2.8 mm                 │
        │    ⚠ confirm 5 boundary symbols                  │
        │    17 tests pass       [Approve]  [Reject]       │
        └──────────────────────────────────────────────────┘
        ↓
new version + new hash  →  deployed
```

**Nobody retypes the law.** A person reads a before/after comparison and clicks.

Cost: **one day to set up, once. A few minutes per amendment after that.**

---

## 5. Why bindings point at an address, not at numbers

This is the idea that makes the whole thing maintainable.

```
BAD    check "minimum height" → 2.5 mm            every change needs a code edit
GOOD   check "minimum height" → lmpc/r7/table-I   the address never moves
```

`lmpc/r7/table-I` means *rule 7, Table-I*. When an amendment replaces that table's
contents, the address is unchanged — so the binding is untouched and **the new numbers just
load**. Ten thresholds update with zero human editing.

A binding only needs revisiting when a genuinely **new kind** of rule appears — roughly
once or twice a year.

---

## 6. Why the repealed law is kept

A packet inspected in 2017 must be judged by 2017's rule, not today's.

```
Same 2.2 mm label, 500 g pack, 215 cm² panel:

  31 Dec 2017   PASS   2.0 mm required   (old table, keyed to weight)
  01 Jan 2018   FAIL   2.5 mm required   (new table, keyed to panel size)
```

So every check carries **dated versions**, and the engine picks the one in force on the day
the photo was taken. Deleting repealed law would make every old finding unreproducible —
and a new amendment would silently rewrite last year's reports.

---

## 7. When the build refuses

The build produces **no rulepack at all** in any of these cases. This is the safety net.

| It refuses when… | Because |
|---|---|
| A notification in the chain is missing and unexplained | We cannot prove the pack is current |
| A gap is recorded but has no named reviewer | Someone must own the decision |
| A recorded gap touches a rule we actually check | A note cannot stand in for the document |
| The gazette numbers differ from what a reviewer approved | The law moved under us |
| The table has a different number of rows than approved | Same |
| A rule names a checker nobody wrote | It would fail silently on every scan in the field |

And after the build: the app **re-checks the fingerprint every time it loads the pack**. If
a single threshold has been edited on disk, it refuses to run. Every verdict cites that
hash, so a quiet edit would forge the legal basis of past findings.

---

## 8. Known honesty markers inside the pack

The pack does not pretend to be more certain than it is.

| Marker | Meaning |
|---|---|
| `boundary_confirmed_by_human: false` | The gazette's own text layer drops the `≤` symbol, so `A ≤ 50` reads as `A < 50`. All five rows await a human check, and anything near a boundary abstains |
| `verdict_ceiling: INDETERMINATE` | This check may measure and explain, but is not allowed to accuse — e.g. the generic name, which has no reliable way to be identified |
| `acknowledged_gaps` | A notification we could not obtain, with the search that was done |
| `unverified_bindings` | Rules traced to the 2011 base text, which is still an un-OCR'd scan |

---

## 9. Who touches what

| Who | What | How often |
|---|---|---|
| Engineer | The 12 checkers, in code | Once; then only for a genuinely new kind of rule |
| Reviewer (two people) | `bindings.yaml` — confirm numbers against the page image | One day at setup |
| Reviewer | Approve an amendment diff | A few minutes, per amendment |
| Nobody | The rulepack file itself | **It is generated. Never hand-edit it** |

---

## 10. In one paragraph

The law is compiled, not transcribed. A compiler downloads the gazette notifications,
proves the chain back to the base rules is unbroken, parses each amendment into an
operation against a stable address, and lifts the numbers straight out of the tables. A
human points each rule at one of twelve checkers once, then only ever approves diffs. The
result is a small, dated, hash-addressed file that carries its own evidence of currency —
including what it could not obtain and what it is not allowed to conclude. The running app
executes that file and nothing else.
