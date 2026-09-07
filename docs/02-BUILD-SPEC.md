# Build Specification — Legal Metrology Compliance System

**Version 2.0 · 2026-09-07 · supersedes `archive/2026-09-engineering-spec-superseded.md`
and `archive/2026-09-technical-spec-superseded.md`.**

This is the single implementation document. Every value, threshold, refusal path and data
shape needed to build the system is here. Where a number appears, it was measured, not
assumed; where a rule appears, it was read from the gazette, not remembered.

Everything below was validated against **140 real product photographs**, **48 real gazette
instruments**, and **2,940 real rule evaluations**. The defects that shaped it are listed
in Part M — read that before disagreeing with a design choice, because most of them look
over-cautious until you see what they prevent.

---

## Contents

| Part | Subject |
|---|---|
| 0 | Principles — the eight rules everything else follows from |
| A | The law compiler: gazette PDFs → a versioned, hashed rulepack |
| B | Capture: guided photography and the coverage assertion |
| C | Vision and OCR |
| D | Extraction — no language model |
| E | The rule engine |
| F | Evidence, reports, repository |
| G | API and database |
| H | Web and mobile clients |
| I | Security, roles, audit |
| J | Deployment and performance budget |
| K | Testing |
| L | Rule catalogue — all 21 checks and 4 gates |
| M | Defect register — 17 defects found by testing |
| N | Open questions |

---

## Part 0 — Principles

These are not aspirations. Each is enforced by code and covered by a test, and each exists
because its absence produced a wrong legal conclusion during validation.

**P1 — The law is compiled, never read at runtime.**
Gazette PDFs are build-time inputs. The deployed system executes a rulepack: a few
kilobytes of parameters with a content hash. No scan ever touches a PDF, a website, or a
search index. *Rationale: retrieval at verdict time can surface a repealed amendment, a
Hindi rendition, or a draft that never commenced.*

**P2 — Identity is (number, year), never the number.**
G.S.R. numbers restart annually and collide within a decade. `G.S.R. 875(E)` is both the
General Rules amendment of 9 Sep 2016 and the breath-analyser amendment of 28 Nov 2025,
and both are cited as predecessors by different instruments in the live corpus.

**P3 — Six verdicts, not two.**
`PASS · FAIL · INDETERMINATE · NOT_APPLICABLE · REVIEW_REQUIRED · SYSTEM_ERROR`.
"We could not find the MRP" and "the MRP is missing" are different findings and must never
collapse into one.

**P4 — Absence requires asserted coverage.**
A declaration not found is only a violation when the capture flow has confirmed every
surface was photographed *and* every region was legible. An image labelled "back" by a
third party is not an assertion.

**P5 — Different claims need different confidence.**
*"There is text here"* survives a misread glyph — threshold 0.80.
*"This character is wrong, therefore the form is violated"* turns on a single glyph — 0.95.
*"Thirty characters of required wording are absent"* is robust again — 0.80.

**P6 — Measure the thing the rule names, or abstain.**
Rule 7(3) compares a letter's width to its own height. A detection box spans ascenders,
descenders and padding. Measuring the box carefully still measures the wrong thing.

**P7 — Repealed law is retained, never deleted.**
A finding is reproducible only while the version that governed it still exists inside the
rulepack. A scan is judged by the law in force on its capture date.

**P8 — There is no language model in the deployed system.**
The problem statement specifies rule-based checking. Vision AI (PP-OCR) produces
*evidence*; deterministic Python draws every *conclusion*.

---

## Part A — The Law Compiler

Turns gazette PDFs into `rulepack/current.json`. Runs offline, on a build machine, never
in the request path.

```
fetch → classify → extract text → identify → chain → families → parse ops
      → extract tables → cross-check against reviewer → bind → hash → publish
```

### A.1 Source registry

| Field | Type | Notes |
|---|---|---|
| `url` | text | Always rewrite `http://` → `https://`; port 80 does not answer |
| `family` | text | `PACKAGED_COMMODITIES`, `GENERAL`, `GATC`, … |
| `fetched_at`, `http_status`, `sha256`, `bytes` | | Recorded on every attempt |

**Fetch contract.** TLS verification is disabled for `consumeraffairs.gov.in` (certificate
expired; documented, not silently ignored). Timeout 90 s. Four retries with backoff
`0.4·i + 1.5·(i+1)` seconds. A page that returns HTML where JSON was expected counts as a
failure. **A failed page is skipped, never fatal** — partial data is useful, a lost harvest
is not.

### A.2 Classification

```python
pages = pdfinfo(path)            # 0 if unreadable
text  = pdftotext(-layout)       # None on non-zero exit, timeout, or OSError

if text is None:            kind = "CORRUPT_UNREADABLE"
elif len(text) < 200*pages: kind = "SCANNED_NEEDS_OCR"
else:                       kind = "DIGITAL"
```

`CORRUPT_UNREADABLE` and `SCANNED_NEEDS_OCR` documents are recorded and **excluded from the
chain** — never half-parsed. A partially recovered gazette is worse than a missing one.

*Measured on the live corpus: 22 of 30 Packaged Commodities instruments are digital; all 8
scans are 2011–2015. 18 of 18 General Rules / GATC instruments are digital.*

### A.3 Text extraction and language split

Gazette notifications print Hindi first, then English. Keep a line when Devanagari
characters are **≤ 15 % of its alphabetic characters**:

```python
DEV = re.compile(r"[ऀ-ॿ]")
keep = len(DEV.findall(line)) / len([c for c in line if c.isalpha()]) <= 0.15
```

### A.4 Instrument identity  *(P2)*

```python
GSR      = r"G\.S\.R[.\s]*(?:number[.\s]*)?\d+\s*\(\s*E\s*\)"
SELF_RE  = rf"{GSR_CAP}\s*[.—–:\-]"                  # tolerates "G.S.R. . 778(E)"
SELF_DATE= rf"New\s+Delhi,?\s+the\s+{DATE}"
DATE     = r"(\d{1,2}\s*(?:st|nd|rd|th)?\s+[A-Z][a-z]+,?\s+\d{4})"   # "30 th August, 2023"

key = f"{gsr}@{year}"                                 # G.S.R. 875(E)@2016
```

Real defects the patterns must absorb, all observed in the live corpus:
`G.S.R. . 778(E)` (stray period in the gazette), `30 th August` (pdftotext splits the
ordinal), `2022were published` (missing space in the source).

**Collision detection is mandatory.** Group by number; any number resolving to more than
one key is reported in `gsr_number_collisions` and surfaces in the build log.

### A.5 The closing note and the chain

Every instrument ends with its lineage:

> *The principal rules were published … vide number G.S.R. 202(E), dated the 7th March,
> 2011 and was last amended vide number G.S.R. 312(E), dated 27th April, 2026.*

```python
NOTE_RE = (rf"(?P<parent>principal rules|.{{0,90}}?Rules,\s*\d{{4}}).{{0,40}}?were?\s+published"
           rf".{{0,220}}?(?P<bg>{GSR}).{{0,40}}?dated\s+(?:the\s+)?(?P<bd>{DATE})"
           rf"(?:.{{0,220}}?last\s+amended[,\s]*(?:vide)?[,\s]*(?:notification)?[,\s]*(?:number)?"
           rf".{{0,60}}?(?P<pg>{GSR}).{{0,40}}?dated\s+(?:the\s+)?(?P<pd>{DATE}))?")
```

The `last amended` group is **optional** — the first amendment to an instrument has no
predecessor (`is_first_amendment_of_parent`).

**Chain walk = a reachability proof.** Start at the instrument nothing points back to,
follow `prev_key` until the base rules. A pointer to a key not held is a **named missing
document**, not a skipped one.

*Measured: 12 links for Packaged Commodities (G.S.R. 418(E), 29 May 2026 → G.S.R. 60(E),
27 Jan 2023); 13 for General Rules; 4 for GATC.*

### A.6 Family resolution — transitive

An instrument may amend the principal rules, or amend an earlier amendment of them. Both
belong to the same family and the chain runs straight through both.

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

Grouping on the *declared* parent instead splits one chain into fragments and reports gaps
that are not gaps. *Measured: General Rules went from 4 reconstructed links to 13.*

### A.7 Amendment operation grammar

Gazette language is a closed register. Verbs to support:

| Phrase | Operation |
|---|---|
| `for X, the following … shall be substituted` | `substitute` |
| `after X, the following … shall be inserted` | `insert` |
| `X shall be omitted` | `omit` |
| `X shall be numbered / renumbered` | `renumber` |
| `for the words …, the words … shall be substituted` | `substitute_words` |

Each operation resolves to a **stable node address**:

```
lmpc/r7/sr2            rule 7, sub-rule (2)
lmpc/r7/table-I        rule 7, Table-I
lmpc/r6/sr1/cle        rule 6, sub-rule (1), clause (e)
```

Node addresses are what bindings attach to. When an amendment substitutes a node's
contents, parameters reload and no binding changes.

*Measured: 56 operations across the 30-document Packaged Commodities corpus; 30 across the
18-document General/GATC corpus. Roughly one third resolve to `lmpc/?` because the rule
number sits in a preceding sentence — see Part N.1.*

### A.8 Table extraction

```python
ROW = r"^\s*(\d)\s+(?P<cond>[0-9]+\s*[<≤>=]+\s*A|A\s*[<≤>=]+\s*[0-9]+|
                    [0-9]+\s*[<≤>=]+\s*A\s*[<≤>=]+\s*[0-9]+)\s+
       (?P<h>\d+\.\d)\s+(?P<m>\d+\.\d)\s*$"
```

The table is printed twice (Hindi and English renditions) — de-duplicate on
`(band, min, molded)`.

**Every row is emitted with `needs_human_confirmation = ("≤" not in band)`.** The 2017
gazette's embedded font drops the `≤` glyph, so `A ≤ 50` extracts as `A < 50`. Boundary
operators are exactly the values that get litigated. Production must crop the table region
from the **page image** and show it beside the parsed values in the approval screen.

### A.9 Gap register — `lawc/gaps.yaml`

A chain hole fails the build unless a human has recorded the search:

```yaml
gaps:
  - gsr: "G.S.R. 910(E)"
    dated: "2022-12-29"
    referenced_by: "G.S.R. 60(E)"
    searched:
      - {source: "consumeraffairs.gov.in/pages/legal-metrology-act", on: "2026-09-07", result: NOT_LISTED}
    assessment: >
      Lies on the compliance-deadline branch; no binding depends on a node it touches.
    affects_nodes: []            # a non-empty intersection with bound nodes FAILS the build
    decision: ACCEPT_WITH_DISCLOSURE
    reviewer: "akshaj.tiwari"
    reviewed_on: "2026-09-07"
    disclosure: >
      One instrument in the amendment chain is not published on the DoCA website …
```

The disclosure travels inside the rulepack and prints on **every report**. This is
deliberately noisy: an unrecorded gap fails the build, a recorded one is visible forever.

*G.S.R. 910(E) of 29 December 2022 is genuinely absent from all 93 PDF links on the
government page. The tool found this by reachability, not by anyone noticing.*

### A.10 Bindings — `lawc/bindings.yaml`

The one-time human work: point each legal requirement at a generic operator and record
what a reviewer confirmed.

```yaml
- check: LMPC-R7-2-MIN-HEIGHT
  node: lmpc/r7/table-I            # bindings attach to the NODE, not to values
  clause: "Rule 7(2) Table-I"
  operator: table_lookup
  effective_from: 2011-04-01       # when the REQUIREMENT began
  table_effective_from: 2018-01-01 # when THIS table came into force
  citation: {gsr: "G.S.R. 629(E)", page: 11, dated: "2017-06-23"}
  params:
    input: pdp_area_cm2
    compare: glyph_height_mm
  boundary_review:
    status: UNRESOLVED
    policy: guard_band
    guard_band_cm2: 0.5
  superseded:                      # repealed law is retained (P7)
    - effective_from: 2011-04-01
      effective_to: 2017-12-31
      keyed_by: net_quantity_g
      rows: [{upper: 200, min_mm: 1.0, molded_mm: 1.0}, …]
  confirmed_values:                # build FAILS if the gazette disagrees
    - {upper_cm2: 50, min_mm: 1.0, molded_mm: 1.5}
    …
```

### A.11 Build refusal matrix

The build produces **no rulepack at all** in any of these states. Each is covered by a test.

| # | Condition | Message |
|---|---|---|
| 1 | Chain hole not in `gaps.yaml` | *cannot be proven current* |
| 2 | Acknowledged gap with no named reviewer | *named reviewer* |
| 3 | Gap whose `affects_nodes` intersects a bound node | *cannot stand in for the document* |
| 4 | Gazette table values ≠ `confirmed_values` | *a human must re-review* |
| 5 | Gazette table row count ≠ confirmed row count | *rows* |
| 6 | A binding names an operator that is not implemented | *unimplemented operators* |
| 7 | No amendment in the corpus substitutes a bound table node | *no amendment … substitutes* |
| 8 | Empty corpus | fetch failure propagates |

Warnings (build proceeds, printed and stored): unreadable files; bindings not traceable to
a corpus amendment (currently 12, all tracing to the base 2011 rules — see N.2).

### A.12 Rulepack format

```jsonc
{
  "rulepack": "lmpc", "schema": 1,
  "version": "lmpc-2026-09-07-4c38a851",
  "sha256": "4c38a851…",                  // over everything except sha256/version/built_at
  "built_at": "2026-09-07T…Z",            // set AFTER hashing — reproducibility (A.13)
  "currency": {
    "newest_instrument": "G.S.R. 418(E)",
    "chain_links_verified": 12,
    "chain_complete": false,
    "acknowledged_gaps": [ { "gsr": …, "reviewer": …, "text": … } ],
    "corpus_documents": 30,
    "documents_needing_ocr": 8,
    "unreadable_documents": [],
    "chain": [ {"gsr": …, "prev": …, "prev_date": …} ]
  },
  "gates":  [ … 4 … ],
  "checks": [ … 21 … ],
  "modes":  { "PHYSICAL_PACKAGE": {...}, "ECOMMERCE_LISTING": {"excludes": [...]} },
  "unverified_bindings": [ "lmpc/r3", … ]
}
```

### A.13 Integrity and reproducibility

- `digest(pack)` hashes everything except `sha256`, `version`, `built_at`.
- `built_at` is assigned **after** hashing — the same corpus must hash identically on any
  machine at any time, or reproducibility is a claim without a mechanism.
- `load()` recomputes the digest and **raises on mismatch**. Every verdict cites this hash;
  a silent edit would forge the legal basis of past findings.
- Tested: two builds of one corpus produce one hash; a weakened threshold is refused at
  load.

---

## Part B — Capture

### B.1 Guided capture state machine

```
IDLE → FRONT → BACK → SIDE_1 → SIDE_2 → SCALE_REF → REVIEW → SUBMIT
                 ↑ each state accepts a frame only after B.2 passes
```

The officer is told which surface to photograph. A state cannot be skipped; it can be
**explicitly waived**, which is recorded and *withholds the coverage assertion*.

### B.2 Frame quality gates — on device, before acceptance

| Gate | Method | Reject when |
|---|---|---|
| Blur | variance of Laplacian | `< 100` |
| Glare | fraction of pixels `> 250` | `> 3 %` of frame |
| Exposure | mean luminance | `< 40` or `> 215` |
| Perspective | detected package quad skew | corner angles deviate `> 20°` |
| Resolution | long edge | `< 1200 px` |

Rejection is immediate and names the problem ("too blurry — hold still"). Diagnosing a bad
photo after upload wastes the officer's trip.

### B.3 The coverage assertion  *(P4)*

```python
scan.coverage_asserted = (
    all(state.completed for state in REQUIRED_PANELS)
    and not any(state.waived for state in REQUIRED_PANELS)
)
```

`coverage_asserted=False` makes every presence check return `INDETERMINATE` instead of
`FAIL`. This is what turns "use guided capture" from a plan item into an enforced
constraint. Third-party images always carry `False`.

### B.4 Scale reference

| Type | Source of truth | Notes |
|---|---|---|
| `ISO_ID1_CARD` | long edge = 85.60 mm | any bank card; free and always available |
| `APRILTAG_36H11` | printed marker, known side | best accuracy, needs a printed card |
| `MANUAL_DIMENSIONS` | officer enters L×W×H in cm | fallback; secondary evidence only |
| `NONE` | — | **every millimetre check returns `INDETERMINATE`** |

The marker must be **coplanar with the measured panel**. A non-coplanar marker abstains.

---

## Part C — Vision and OCR

### C.1 Resolution budget — measured, not assumed

Real phone photographs in the validation corpus reach **9248 × 6936 (64 MP)**. Handing one
to the recogniser exhausts memory and never returns.

```python
MAX_EDGE = 1800
im.draft("RGB", (MAX_EDGE, MAX_EDGE))    # JPEG decoder downscales while decoding
im = im.convert("RGB")
if max(im.size) > MAX_EDGE:              # LANCZOS lands exactly on the cap
    im = im.resize(scaled, Image.LANCZOS)
```

Measured on 10 products, 4 settings:

| Long edge | s/photo (GPU) | Regions | MRPs found |
|---|---|---|---|
| 800 | 0.8 | 452 | 1/10 |
| 1280 | 0.9 | 514 | 1/10 |
| 1800 | 1.6 | 528 | 2/10 |
| 2400 | 2.3 | 558 | **3/10** |

Accuracy rises with resolution at roughly proportional cost, with no sweet spot.
**Default 1800; use 2400 on the server where latency allows.**

### C.2 Engine selection

```python
CUDA = "CUDAExecutionProvider" in onnxruntime.get_available_providers()
# GPU: rewrite config.yaml with Det/Cls/Rec use_cuda=true, pass config_path
# CPU: default construction
```

Measured on an RTX 3050 6 GB: a dense 50 MP ingredients panel goes from *never finishing*
to **2.3 s**. **The CPU figure governs field devices; the GPU figure governs the server.**
A dense panel alone breaks a 30-second budget on CPU — the server needs a GPU.

### C.3 Token model

```python
@dataclass
class Token:
    text: str
    x: int; y: int; w: int; h: int       # in the RESIZED frame
    conf: float                          # RapidOCR returns a STRING — cast
    panel: str                           # FRONT | BACK | SIDE | TOP | BOTTOM
    cap_height_px: float | None          # h * 0.62 — a documented bias, not a fact
    src: frozenset                       # provenance: which raw regions this came from
```

Geometry lives in the resized frame. Every check that uses it is a **ratio**, so a uniform
scale cancels. Absolute millimetre checks do not use these boxes at all.

### C.4 Glyph segmentation — the known gap  *(P6)*

`cap_height_px` is an estimate. Rule 7(3) needs per-letter width and height, which
detection boxes cannot supply. Until a segmentation pass exists,
`scan.glyph_segmentation = False` and the width-ratio check abstains.

*It produced 11 false accusations at plausible values like 0.151 before this gate existed.*

---

## Part D — Extraction (no language model)

Five jobs a language model would conventionally absorb, each handled by a small
deterministic component.

| Job | Mechanism | Library |
|---|---|---|
| Identify which text is the MRP | lexicon + scored rubric | `rapidfuzz` |
| Read a mangled heading | normalised edit distance ≥ 85 | `rapidfuzz` |
| Phrase a finding | templated strings in `rules.yaml`, en + hi | `str.format` |
| "Which documents affect Rule 6?" | SQL over the operation ledger | Postgres FTS |
| Propose amendment operations | gazette grammar parser (A.7) | `re` |

### D.1 Layout assembly — mandatory

Real OCR splits an anchor from its value (`"NET WEIGHT :"` here, `"220"` three centimetres
right) and collapses spaces inside others (`"MRPRS.10/-(INCL.OFALLTAXES)"`).
**An extractor that assumes one region per declaration finds 0 MRPs in 60 real products.**

```python
same_line(a, b) = a.panel == b.panel and
                  overlap_y(a, b) > 0.45 * min(a.h, b.h)
max_gap = 6.0 * line_height        # beyond this, a far column is not the same statement
```

Candidates generated per scan:
1. every raw region
2. every assembled line
3. every assembled line **respaced** (letter↔digit and camel boundaries)
4. every line joined with the line below (`gap ≤ 1.2 × line height`) — labels wrap

Producing more candidates cannot fabricate a declaration: a candidate is still recognised
text with real geometry.

### D.2 Lexicon

Curated synonyms per field, English and Devanagari. Matching is
`rapidfuzz.partial_ratio` — the question is whether the line *contains* a recognisable
spelling, not whether it equals one. Needles shorter than 3 characters are skipped.
Acceptance threshold **85**.

### D.3 Scoring rubric — full weights

```
anchor            = 40 · sim/100        if sim ≥ 85
                    12 · sim/100        otherwise
value_pattern     = +25   (field-specific parse succeeds)
cotext_taxes      = +20   ("incl. of all taxes" near an MRP)
on_pdp            = +8    (token is on the FRONT panel)
not_a_price       = −18   (a price on a net-quantity candidate)
negative_context  = −30   (ingredients / nutrition / storage / directions)
low_ocr_conf      = −25 · (1 − conf)    when conf < 0.80
```

For `mrp`, `require_currency` is relaxed once the anchor matched: real labels print
`MRP: 10.00` with no "Rs.", and recognisers turn `Rs` into `R` or `R5`.

### D.4 Provenance-aware margin

```python
FLOOR     = 45.0    # below this, nothing was really found
MARGIN    = 12.0    # closer than this, two candidates are indistinguishable
NEAR_MISS = 28.0    # above this, SOMETHING resembling the field was on the label

second = first candidate whose `src` is disjoint from the winner's
```

The runner-up must be **materially different**. A line and its respaced rewriting describe
the same pixels; treating them as rivals makes every field ambiguous and abstains on
everything.

Below `FLOOR` or below `MARGIN` → the field is `None`, and diagnostics
(`top`, `margin`, `best_text`, `conf`) are retained so a presence check can distinguish
*missing* from *unreadable* from *ambiguous*.

### D.5 Normalisation

| Field | Output | Notes |
|---|---|---|
| `mrp` | `{amount, currency}` | digit-confusion tolerant inside the numeral only |
| `net_quantity` | `{value, unit, as_printed}` | canonical to `g` / `ml` / `n` |
| `mfg_date` | `{month, year}` | `MM/YYYY` or month name + year |

Every parser is **total**: it returns `None` rather than guessing, because a guessed value
becomes a legal finding.

### D.6 OCR repair — scoped

```python
_OCR_FIX = {O→0, o→0, l→1, I→1, S→5, B→8}     # G→6 and Z→2 REMOVED (M.9)
_NUMERIC_RUN = r"[0-9OolISB.,]{2,}"           # only runs already containing a digit
```

Global translation breaks the words the rule depends on: `Rs.` → `R5.`, `incl.` → `inc1.`.
Repair is applied only inside numeric runs, then separately as separator re-insertion.
**A match that appears only after repair yields `INDETERMINATE`** — the reading is in
doubt, not the label. Repaired candidates carry `repaired=True`, and every operator that
reads a *value* refuses them: repair exists to LOCATE a declaration, never to READ it.
Without that rule, respacing `4S.3s` into `4 S.3 s` let the parser read `4`, call it
rounded, and pass an unrounded price (M.17).

---

## Part E — The Rule Engine

### E.1 Verdict algebra

| Verdict | Meaning | May a check reach it automatically? |
|---|---|---|
| `PASS` | Requirement met | Yes |
| `FAIL` | Requirement violated | Only with asserted coverage, legible evidence, and confidence above the claim's threshold |
| `INDETERMINATE` | Evidence or law insufficient | Yes — this is the default under doubt |
| `NOT_APPLICABLE` | Rule does not govern this package, mode or date | Yes |
| `REVIEW_REQUIRED` | Lawful in one specific reading; a person must look | Yes |
| `SYSTEM_ERROR` | Our bug | Yes — never surfaces as a finding against a trader |

### E.2 Evaluation order — gates first, always

```
1. applicability gates          → NOT_APPLICABLE ends evaluation
2. mode exclusions (Rule 6(10)) → NOT_APPLICABLE
3. temporal filter (E.3)        → NOT_APPLICABLE
4. per-check conditions         → NOT_APPLICABLE
5. operator dispatch            → PASS / FAIL / INDETERMINATE / REVIEW_REQUIRED
6. verdict ceiling (E.6)
```

Running a declaration check on an exempt package is how an automated system accuses
someone of breaking a rule that never applied to them.

### E.3 Temporal selection  *(P7)*

```python
def in_force(spec, on):
    d = date.fromisoformat(on)
    return (not spec.get("effective_from") or d >= date(spec["effective_from"])) and \
           (not spec.get("effective_to")   or d <= date(spec["effective_to"]))
```

Applies to **checks** and to **table versions independently**. Rule 7(2) has required a
minimum height since 2011; only the table changed in 2017. Dating the check to 2018 would
wrongly report "no such rule" for a 2015 inspection.

```
A 2.2 mm label on a 500 g pack, 215 cm² panel:
  31 Dec 2017 → PASS  (2.0 mm required, net-quantity table)
  01 Jan 2018 → FAIL  (2.5 mm required, panel-area table)
```

### E.4 The operators

Twelve implementations, six archetypes. Parameters come from the rulepack; the code never
moves when the law does.

**`presence(field)`**
```
field found                       → PASS
not scan.coverage_asserted        → INDETERMINATE  (P4)
required panels not captured      → INDETERMINATE
diag.top ≥ NEAR_MISS              → INDETERMINATE  "resembles it but not identifiable"
any token conf < LEGIBLE          → INDETERMINATE  "absence from an unreadable image"
otherwise                         → FAIL
```

**`format_regex(field, regex, [phrase_any])`**
```
regex matches raw                 → check phrase (below) or PASS
matches only after repair         → INDETERMINATE  (which repair is named)
min token conf < ACCUSE (0.95)    → INDETERMINATE  (P5)
otherwise                         → FAIL

phrase similarity ≥ phrase_present_at (85)  → PASS
             < phrase_absent_below (60) and conf ≥ LEGIBLE (0.80) → FAIL
             in between                      → INDETERMINATE
```
Legal *wording* is matched fuzzily; *digits* are matched exactly. The digits are the
finding; the words are the context.

**`numeric_predicate(field, predicate)`**
```
numeral span not consumed end-to-end → INDETERMINATE   (M.7: "45.b0" parsed as 45.0)
numeral contains confusable chars    → INDETERMINATE
conf < LEGIBLE                       → INDETERMINATE
otherwise                            → predicate(amount)
```

**`table_lookup(input, compare)`**
```
pdp_area unknown        → INDETERMINATE "dimensions not supplied"
no scale reference      → INDETERMINATE "millimetre height cannot be measured"
select version in force on scan.captured_at
if version keyed to net_quantity → use that path
area within guard_band of a band edge and boundary_review UNRESOLVED
                        → INDETERMINATE (names the boundary)
|measured − required| ≤ 1 px expressed in mm → INDETERMINATE
otherwise               → measured ≥ required ? PASS : FAIL
```

**`ratio_min(numerator, denominator, min)`**
```
not scan.glyph_segmentation → INDETERMINATE  (P6, M.14)
composite token (len(src)>1) → skipped
ratio outside [0.05, 3.0]    → INDETERMINATE "detection artefact"
only MANDATORY declaration fields are measured (M.15)
```

**`clear_space(field, above_below, left_right)`**
```
composite quantity token → INDETERMINATE
any measured distance < 0 → INDETERMINATE "regions overlap"
otherwise → both distances ≥ multiples × numeral height ? PASS : FAIL
```

**`applicability`, `cross_field`, `tiered_format`, `script_allowed`, `mrp_uniqueness`,
`date_plausible`, `small_package_mark`** — see Part L for parameters.

### E.5 Confidence thresholds  *(P5)*

```python
LEGIBLE   = 0.80    # below: a token supports no finding at all
ACCUSE    = 0.95    # below: no CHARACTER-LEVEL accusation
NEAR_MISS = 28.0    # score above which "something like it" was present
```

*One threshold for all claims produced either false accusations (set low) or silent misses
(set high). Three thresholds gave 0 % false accusations and 0 missed violations
simultaneously.*

### E.6 Verdict ceilings

| Ceiling | Effect |
|---|---|
| `INDETERMINATE` | The check may measure and explain but never `FAIL`. Used where extraction is not reliable enough to accuse — e.g. the generic name, which has no lexical anchor. |
| `INDETERMINATE_NEAR_BOUNDARY` | Enforced **inside** `table_lookup`, which knows where the boundaries are. Not a blanket cap. |

### E.7 Overall status

```
SYSTEM_ERROR        if any SYSTEM_ERROR
NON_COMPLIANT       elif any FAIL
REVIEW_REQUIRED     elif any REVIEW_REQUIRED
INCOMPLETE_EVIDENCE elif any INDETERMINATE
OUT_OF_SCOPE        elif every result NOT_APPLICABLE
COMPLIANT           otherwise
```

---

## Part F — Evidence, Reports, Repository

### F.1 Evidence integrity

- Original frames written to object storage **before** processing, addressed by SHA-256,
  never mutated. Derived images (crops, overlays) are separate objects.
- Every `Result` carries `check, clause, verdict, reason, citation{gsr,page,dated},
  evidence{…}`.
- Every scan stores an **execution manifest**: rulepack version + hash, model files +
  hashes, container digest, `MAX_EDGE`, git SHA, input hashes. A run is replayable.

### F.2 Report

Sections, in order: identification · overall status · scan metadata · per-check table
(clause, verdict, measured value, required value, citation) · annotated evidence crops ·
officer notes · reviewer sign-off · **chain-gap disclosures** · rulepack version and hash.

PDF via WeasyPrint, DOCX via docxtpl, both rendered from **one verdict object** — not a
PDF→DOCX conversion. Report content is hashed and versioned; re-finalising creates v2.

### F.3 Repository

`products` deduplicated on `lower(brand || '|' || manufacturer_id || '|' || barcode)` as a
stored generated column. Barcode data is **convenience only** — it pre-fills officer
fields and never enters `extracted_declarations` or reaches the rule engine. If a registry
says ₹45 and the label says ₹40, the label governs.

---

## Part G — API and Database

### G.1 REST surface (`/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/login` · `/auth/refresh` · `/auth/logout` | JWT access + revocable refresh |
| GET | `/auth/me` | role + jurisdiction |
| POST | `/scans` | multipart; `client_uuid` is the idempotency key → `202 {scan_id}` |
| GET | `/scans/{id}` | images, declarations, evaluations, status |
| GET | `/scans` | search: manufacturer, brand, category, status, dates, officer, jurisdiction, violation type, `q` |
| PATCH | `/scans/{id}` | relink product, correct package shape |
| POST | `/scans/{id}/reevaluate` | new evaluation batch; never touches a finalised report |
| GET | `/scans/{id}/evaluations` | with evidence |
| POST | `/scans/{id}/evaluations/{eid}/override` | `{outcome, reason}` → append-only record |
| POST | `/scans/{id}/report` | finalise → PDF + DOCX |
| GET | `/reports/{id}/download?format=pdf\|docx` | signed URL |
| GET/POST | `/rules`, `/rules/{code}/versions`, `/rules/{id}/approve` | rulepack admin |
| GET | `/rules/watch/pending` | compiler proposals awaiting approval |
| GET | `/dashboard/summary` · `/violations-by-type` · `/top-non-compliant` · `/geo` | |
| POST | `/sync/scans/batch` | offline batch; per-item `created \| duplicate_ignored \| conflict` |

Errors: `{"error": {"code", "message", "details"}}`.

### G.2 Schema (PostgreSQL 16)

```sql
CREATE TABLE jurisdictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(150) NOT NULL, state VARCHAR(100) NOT NULL,
    parent_jurisdiction_id UUID REFERENCES jurisdictions(id));

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(200) NOT NULL, email VARCHAR(255) UNIQUE NOT NULL,
    role VARCHAR(30) NOT NULL CHECK (role IN
        ('FIELD_OFFICER','REVIEWING_OFFICER','ADMIN','AUDITOR')),
    jurisdiction_id UUID REFERENCES jurisdictions(id),
    password_hash TEXT, is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now());

CREATE TABLE commodity_categories (
    code VARCHAR(50) PRIMARY KEY, name VARCHAR(150) NOT NULL,
    fssai_overlap BOOLEAN DEFAULT FALSE, default_exemptions JSONB);

CREATE TABLE manufacturers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL, registered_address TEXT,
    external_registry_ref VARCHAR(100), created_at TIMESTAMPTZ DEFAULT now());

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_name VARCHAR(255), manufacturer_id UUID REFERENCES manufacturers(id),
    category_code VARCHAR(50) NOT NULL REFERENCES commodity_categories(code),
    barcode VARCHAR(50), declared_net_quantity VARCHAR(50),
    dedup_key VARCHAR(500) GENERATED ALWAYS AS (lower(
        coalesce(brand_name,'')||'|'||coalesce(manufacturer_id::text,'')||'|'||
        coalesce(barcode,''))) STORED,
    UNIQUE (dedup_key));

CREATE TABLE scans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID REFERENCES products(id),
    officer_id UUID NOT NULL REFERENCES users(id),
    jurisdiction_id UUID REFERENCES jurisdictions(id),
    mode VARCHAR(20) NOT NULL CHECK (mode IN ('PHYSICAL_PACKAGE','ECOMMERCE_LISTING')),
    package_shape VARCHAR(20) CHECK (package_shape IN
        ('RECTANGULAR','CYLINDRICAL','IRREGULAR')),
    scale_reference_type VARCHAR(20) CHECK (scale_reference_type IN
        ('ISO_ID1_CARD','APRILTAG_36H11','MANUAL_DIMENSIONS','NONE')),
    scale_reference_data JSONB, pdp_area_cm2 NUMERIC(10,2),
    -- P4: the assertion that makes absence a finding
    coverage_asserted BOOLEAN NOT NULL DEFAULT FALSE,
    panels_captured VARCHAR(10)[] NOT NULL DEFAULT '{}',
    glyph_segmentation BOOLEAN NOT NULL DEFAULT FALSE,
    captured_at DATE NOT NULL,             -- P7: which law governs
    rulepack_version VARCHAR(60), rulepack_sha256 CHAR(64),
    status VARCHAR(30) NOT NULL DEFAULT 'RECEIVED' CHECK (status IN
        ('RECEIVED','OCR_IN_PROGRESS','OCR_COMPLETE','EXTRACTION_COMPLETE',
         'EVALUATION_COMPLETE','UNDER_REVIEW','FINALIZED','SYNC_CONFLICT')),
    client_uuid UUID UNIQUE, geo_lat NUMERIC(9,6), geo_lng NUMERIC(9,6),
    created_at TIMESTAMPTZ DEFAULT now());

CREATE TABLE scan_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    panel_label VARCHAR(20), storage_key TEXT NOT NULL, sha256 CHAR(64) NOT NULL,
    width_px INT, height_px INT, max_edge_used INT,
    quality JSONB,                          -- blur, glare, exposure, skew
    created_at TIMESTAMPTZ DEFAULT now());

CREATE TABLE extracted_declarations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    scan_image_id UUID REFERENCES scan_images(id),
    field_type VARCHAR(40) NOT NULL, raw_text TEXT, normalized_value JSONB,
    bbox_x INT, bbox_y INT, bbox_w INT, bbox_h INT,
    ocr_confidence NUMERIC(4,3), score NUMERIC(6,2), runner_up_margin NUMERIC(6,2),
    feature_weights JSONB,                  -- why this candidate won
    source_token_ids JSONB, glyph_height_px NUMERIC(8,2), glyph_height_mm NUMERIC(6,2),
    is_on_pdp BOOLEAN, created_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX idx_extracted_scan ON extracted_declarations(scan_id);

CREATE TABLE rule_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    check_code VARCHAR(60) NOT NULL, clause VARCHAR(100),
    outcome VARCHAR(25) NOT NULL CHECK (outcome IN
        ('PASS','FAIL','INDETERMINATE','NOT_APPLICABLE','REVIEW_REQUIRED','SYSTEM_ERROR')),
    reason TEXT NOT NULL, citation JSONB NOT NULL, evidence JSONB,
    rulepack_version VARCHAR(60) NOT NULL, law_version DATE,
    evidence_declaration_id UUID REFERENCES extracted_declarations(id),
    is_override BOOLEAN DEFAULT FALSE,
    override_of_evaluation_id UUID REFERENCES rule_evaluations(id),
    override_reason TEXT, overridden_by UUID REFERENCES users(id),
    evaluated_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX idx_evaluations_scan ON rule_evaluations(scan_id);

CREATE TABLE compliance_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES scans(id), version INT NOT NULL,
    overall_status VARCHAR(24) NOT NULL,
    pdf_storage_key TEXT, docx_storage_key TEXT, content_sha256 CHAR(64),
    reviewed_by UUID REFERENCES users(id), review_notes TEXT,
    finalized_at TIMESTAMPTZ, UNIQUE (scan_id, version));

CREATE TABLE rulepacks (
    version VARCHAR(60) PRIMARY KEY, sha256 CHAR(64) NOT NULL,
    newest_instrument VARCHAR(40), chain_links INT, chain_complete BOOLEAN,
    disclosures JSONB, payload JSONB NOT NULL, published_at TIMESTAMPTZ DEFAULT now(),
    approved_by UUID REFERENCES users(id));

CREATE TABLE amendment_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_key VARCHAR(40) NOT NULL,      -- "G.S.R. 875(E)@2016"  (P2)
    family VARCHAR(40), prev_key VARCHAR(40), op VARCHAR(20), node VARCHAR(80),
    quote TEXT, source_file TEXT, source_sha256 CHAR(64), page INT,
    status VARCHAR(20) DEFAULT 'QUARANTINED'
        CHECK (status IN ('QUARANTINED','APPROVED','REJECTED')),
    approved_by UUID REFERENCES users(id), approved_at TIMESTAMPTZ);
CREATE INDEX idx_ledger_node ON amendment_ledger(node);

CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL, entity_id UUID NOT NULL,
    actor_id UUID REFERENCES users(id), action VARCHAR(50) NOT NULL,
    diff JSONB, occurred_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_manufacturers_name_trgm ON manufacturers USING gin (name gin_trgm_ops);
CREATE INDEX idx_products_brand_trgm ON products USING gin (brand_name gin_trgm_ops);
```

---

## Part H — Clients

### H.1 Web console (Next.js + TypeScript + Tailwind)

`/login` · `/dashboard` · `/scans` · `/scans/new` · `/scans/[id]` · `/scans/[id]/report` ·
`/products/[id]` · `/admin/rules` · `/admin/users`

Key components: `ImageAnnotationViewer` (clickable evidence boxes, colour-coded by
outcome) · `VerdictTable` (clause, outcome, measured vs required, citation, override) ·
`ScoreExplainer` (**the feature weights that chose this candidate**) · `RulepackBanner`
(version, hash, disclosures) · `AmendmentQuarantine` (diff + approve).

The console is an **enforcement workbench**, not a charts page: officers correct
extractions, approve findings, and manage rule versions here.

### H.2 Mobile / PWA

`getUserMedia` capture, on-device quality gates (B.2), guided panel flow (B.1), local
persistence (IndexedDB / SQLite), background sync with `client_uuid` idempotency,
resumable image upload separate from metadata, conflict merge screen.

**The client holds no legal logic.** It captures, gates quality, uploads, and renders what
the server decided.

---

## Part I — Security

- TLS 1.2+ everywhere; HSTS.
- JWT access (15 min) + revocable refresh stored hashed; MFA for `ADMIN`.
- RBAC enforced **server-side on every endpoint** via a central policy table. Jurisdiction
  scoping is a server-derived query filter; a client-supplied jurisdiction may only narrow.
- Upload validation: MIME **and** magic bytes, size cap, virus scan, EXIF GPS stripped
  unless consented.
- Encryption at rest for database and object storage.
- Append-only: `rule_evaluations` overrides, report versions, `audit_log`. Nothing legally
  relevant is hard-deleted.
- Secrets via environment injection from a secrets manager; none in source control.
- CI runs `pip-audit`, `npm audit`, and image scanning.

---

## Part J — Deployment and performance

**Containers:** `api`, `worker-ocr`, `worker-rules`, `worker-reports`, `lawc` (build-time),
`web`, `postgres`, `redis`, `minio`. Docker Compose for pilot; **no Kubernetes**.

**The GPU is not optional on the server.** A dense ingredients panel alone exceeds a
30-second budget on CPU. Worker nodes need CUDA; field devices do not, because they run no
recognition.

Budget for a 4-panel scan at `MAX_EDGE=1800`, GPU:

| Stage | Target |
|---|---|
| Upload acknowledged | < 2 s |
| OCR, 4 panels | ~6 s |
| Layout + extraction | < 0.5 s |
| Rule evaluation | < 0.1 s |
| **Total, p95** | **< 15 s** |

Observability: structured JSON logs correlated by `scan_id`; metrics for queue depth, OCR
latency p50/p95, verdict distribution, **and the false-accusation guard — any FAIL issued
with `coverage_asserted=false` is an alertable bug**.

---

## Part K — Testing

| Suite | Command | Covers |
|---|---|---|
| Unit + integration | `pytest -q` | 45 tests: rulepack integrity, operators, temporal, adversarial |
| Synthetic stress | `python -m stress.run` | 28 scenarios, noise sweep, sensitivity sweep |
| Validation campaign | `python -m stress.campaign` | 24 checks across ingestion, compilation, comparison |
| Real world | `python -m stress.realworld food\|wide` | 140 real products, 394 photographs |
| Resolution | `python -m stress.resolution` | time vs accuracy vs pixel budget |

**Acceptance gates — CI fails on any of these:**

| Gate | Bar | Measured |
|---|---|---|
| Scenario expectations | all met | 28/28 |
| False accusations on compliant labels | ≤ 2 % | **0 %** at 0–40 % character error |
| Violations silently passed | 0 | **0** |
| FAIL without asserted coverage | 0 | **0** in 2,940 real evaluations |
| Campaign checks | all pass | 24/24 |
| Every verdict carries clause + citation + reason | 100 % | 100 % |

**Synthetic labels are rendered at a known DPI with a measured cap height**, so the
expected verdict is derived from physics rather than asserted. Real photographs supply the
failure modes that rendering cannot.

---

## Part L — Rule catalogue

### Gates (evaluated first; a fired gate ends evaluation)

| ID | Clause | Condition | Effect |
|---|---|---|---|
| `GATE-R3-BULK` | Rule 3(a)(b)(c) | > 25 kg / 25 L · cement, fertiliser, farm produce > 50 kg bags · industrial or institutional buyer | Chapter II not applied |
| `GATE-R26-EXEMPT` | Rule 26 | ≤ 10 g / 10 ml (**tobacco carved out**) · restaurant fast food · DPCO formulations · handloom thread in coil | **All rules** not applied |
| `GATE-R26-DRUG-FORMULATION` | Rule 26(c) | DPCO drug formulation, unless a medical device declared as a drug | All rules not applied |
| `GATE-R7-5-OTHER-LAW` | Rule 7(5) | Same information required by another law | Skip 7(1)–(4) **except** net weight, RSP, expiry, consumer care |

### Checks

| ID | Clause | Operator | Effective | Notes |
|---|---|---|---|---|
| `LMPC-R6-1-A-MANUFACTURER` | 6(1)(a) | presence | 2011-04-01 | |
| `LMPC-R6-1-B-GENERIC-NAME` | 6(1)(b) | presence | 2011-04-01 | **ceiling `INDETERMINATE`** — no lexical anchor exists |
| `LMPC-R6-1-C-NET-QUANTITY` | 6(1)(c) | presence | 2011-04-01 | |
| `LMPC-R6-1-D-MFG-DATE` | 6(1)(d) | presence | 2011-04-01 | excluded in e-commerce mode |
| `LMPC-R6-1-E-MRP` | 6(1)(e) | presence | 2011-04-01 | |
| `LMPC-R6-1-F-CONSUMER-CARE` | 6(1)(f) | presence | 2011-04-01 | |
| `LMPC-R6-COUNTRY-OF-ORIGIN` | 6(1) | presence | 2011-04-01 | imported goods only |
| `LMPC-R6-1-E-MRP-FORM` | 6(1)(e) | format_regex + phrase | 2018-01-01 | four gazette illustrations; wording fuzzy, digits exact |
| `LMPC-R6-1-E-MRP-ROUNDING` | 6(1)(e) | numeric_predicate | 2018-01-01 | nearest rupee or 50 paise |
| `LMPC-R6-1-C-QTY-FORM` | 6(1)(c) | format_regex | 2011-04-01 | numeral + SI unit |
| `LMPC-R6-1-D-DATE-FORM` | 6(1)(d) | format_regex | 2011-04-01 | MM/YYYY or month name + year |
| `LMPC-R6-1-D-DATE-PLAUSIBLE` | 6(1)(d) | date_plausible | 2011-04-01 | future or pre-commencement → `REVIEW_REQUIRED` |
| `LMPC-R10-PIN-CODE` | 10(1) Expl. 1 | format_regex | 2018-01-01 | six-digit PIN |
| `LMPC-R10-1-SMALL-PACKAGE-MARK` | 10(1) proviso | small_package_mark | 2018-01-01 | ≤ **10 cm³** (raised from 5 in 2017) |
| `LMPC-R6-1-LL-UNIT-SALE-PRICE` | 6(1)(ll) | tiered_format | 2022-04-01 | per g/kg/ml/litre/cm/m/number by quantity |
| `LMPC-R6-3-MRP-STICKER` | 6(3) | mrp_uniqueness | 2011-04-01 | two prices → `REVIEW_REQUIRED`; a lower revised price is lawful |
| `LMPC-R9-4-LANGUAGE` | 9(4) | script_allowed | 2011-04-01 | Devanagari **or** Latin; a third script is never itself a violation |
| `LMPC-R7-3-WIDTH-RATIO` | 7(3) | ratio_min | 2018-01-01 | width ≥ ⅓ height, excluding `1 i I l`; **needs glyph segmentation** |
| `LMPC-R8-CLEAR-SPACE` | 8 | clear_space | 2011-04-01 | ≥ 1× above/below, ≥ 2× left/right of the numeral |
| `LMPC-R7-2-MIN-HEIGHT` | 7(2) Table-I | table_lookup | 2011-04-01 | table versions below |
| `LMPC-XF-UNIT-PRICE-CONSISTENT` | 6(1)(ll) | cross_field | 2022-04-01 | ±5 % of MRP ÷ quantity → else `REVIEW_REQUIRED` |

### Rule 7 Table-I — current, G.S.R. 629(E) p.11, in force 2018-01-01

| PDP area A (cm²) | Min height | Blown / formed / moulded |
|---|---|---|
| A < 50 | 1.0 mm | 1.5 mm |
| 50 < A < 100 | 1.5 mm | 3.0 mm |
| 100 < A < 500 | 2.5 mm | 4.0 mm |
| 500 < A < 2500 | 4.0 mm | 6.0 mm |
| 2500 < A | 6.0 mm | 6.0 mm |

**Table-II was omitted** by the same amendment. All five boundary operators are
`needs_human_confirmation: true`.

### Rule 7 Table-I — repealed, retained for pre-2018 inspections

| Net quantity | Min height |
|---|---|
| ≤ 200 g/ml | 1.0 mm |
| ≤ 1 kg/l | 2.0 mm |
| above | 4.0 mm |

### Rule 7(4) — PDP area

| Shape | Area |
|---|---|
| Rectangular | height × width of the PDP face |
| Cylindrical | **0.40 × height × circumference** |
| Any other | 0.40 × total surface |

Excluding top, bottom, can flanges, and bottle/jar shoulders and necks.

---

## Part M — Defect register

Seventeen defects found by testing. Each produced a wrong legal conclusion from working code.

| # | Defect | Found by | Fix |
|---|---|---|---|
| M.1 | Verdict ceiling suppressed **every** font violation, not only boundary cases | synthetic stress | ceilings name what they cap |
| M.2 | Absence concluded from an unreadable image — **60 % of compliant labels accused** at 5 % error | noise sweep | absence needs legible evidence + near-miss check |
| M.3 | Format checks failed on OCR damage (`MRP Rs. 4S.00`) | noise sweep | scoped repair; match after repair → `INDETERMINATE` |
| M.4 | Global repair corrupted neighbours: `Rs.`→`R5.`, `incl.`→`inc1.` | noise sweep | repair only inside numeric runs |
| M.5 | Legal wording matched exactly; `incl. of gll taxes` failed a compliant label | noise sweep | wording fuzzy, digits exact |
| M.6 | One threshold for all claims: false accusations or silent misses | sensitivity sweep | three thresholds (P5) |
| M.7 | Partial parse passed an unrounded price: `45.b0` → `45.0` | sensitivity sweep | numeral must be consumed end to end |
| M.8 | **Instrument identity was the number alone** — `G.S.R. 875(E)` exists in 2016 **and** 2025, both cited as predecessors | second rule family | identity = (number, year) |
| M.9 | `G`→`6` repair turned `MFG02/2025` into `MF 602/2025` | real corpus | mapping removed |
| M.10 | Rule families merged; walk picked an arbitrary root and invented gaps | second rule family | transitive family resolution |
| M.11 | **Effective dates ignored entirely** — a 2016 package judged by 2018 law | time-travel test | temporal filter + retained repealed tables |
| M.12 | One corrupt PDF killed the entire build | adversarial | unreadable files recorded and excluded |
| M.13 | `built_at` inside the hashed body made builds non-reproducible | adversarial | hash first, stamp after |
| M.14 | **64 MP photos exhausted memory and never returned**; two fix attempts silently no-oped | real photographs | `MAX_EDGE` cap; every edit asserted |
| M.15 | Width ratio measured detection-box height → **11 false accusations** at plausible values; and measured `A QUALITY PRODUCT OF` | real photographs | abstain without glyph segmentation; declarations only |
| M.16 | Third-party image labels treated as coverage → declarations "missing" on unphotographed sides | wide real-world | `coverage_asserted` (P4) |
| M.17 | **Our own repair manufactured a PASS**: respacing `4S.3s` → `4 S.3 s` let the parser read `4`, call it rounded, and pass an unrounded price | campaign regression | value judgements are forbidden on repaired text |

**The pattern:** in four separate rounds, a check answered confidently from a measurement
it should not have trusted. Assume a fifth exists.

---

## Part N — Open questions

| # | Question | Blocks | Owner | Due |
|---|---|---|---|---|
| N.1 | ~⅓ of amendment operations resolve to `lmpc/?` — the rule number sits in a preceding sentence | full auto-consolidation | compiler owner | Week 2 |
| N.2 | 12 bindings trace to the base 2011 rules, which are an un-OCR'd bilingual scan | closing `unverified_bindings` | legal pair | Week 2 |
| N.3 | `<` vs `≤` at all four Table-I boundaries; the text layer drops `≤` | Rule 7(2) near boundaries | legal reviewer | Week 1 D3 |
| N.4 | Devanagari letter height — is the shirorekha included? | Rule 7(2) on Hindi labels | legal reviewer | Week 1 D5 |
| N.5 | **No real Hindi label has been through the pipeline.** Both real datasets show English-facing panels | Rule 9(4) and all Hindi extraction | data owner | Week 2 |
| N.6 | Glyph segmentation for Rule 7(3) — listed as "build first, no calibration needed", which was wrong | Rule 7(3) verdicts | vision owner | Week 4 |
| N.7 | MRP found on ~50 % of packets where it is legible | shipping | extraction owner | Week 3 |
| N.8 | Qualified legal reviewer for rulepack sign-off | production use | project owner | before pilot |

---

## Appendix — repository layout

```
lmpc/
  lawc/       parse.py · build.py · bindings.yaml · gaps.yaml · fetch.sh
  engine/     model.py · ocr.py · layout.py · lexicon.py · normalize.py
              extract.py · operators.py · engine.py · report.py
  labels/     generate.py (synthetic, exact ground truth) · openfoodfacts.py (real)
rulepack/     current.json  (generated; hash-addressed)
stress/       run.py · campaign.py · realworld.py · resolution.py · scenarios.py
tests/        test_rulepack.py · test_engine.py · test_adversarial.py · test_stress.py
docs/         00-TEAM-BRIEF · 01-ARCHITECTURE · 02-BUILD-SPEC · 03-ENGINEERING-PLAN
              04-FLOW · evidence/ · archive/ · source-extracts/
corpus/       gazette PDFs (git-ignored; fetched by lawc/fetch.sh)
```
