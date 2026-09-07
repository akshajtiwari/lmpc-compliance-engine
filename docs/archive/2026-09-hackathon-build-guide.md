# Build Guide — What we actually make, with what tools

**Hackathon scope. Not production.** Everything here is buildable by 3–6 students in
5 weeks. Where the architecture doc says "signed rulepack with two legal reviewers",
this doc says "a YAML file in git". That is the correct trade for a hackathon.

---

## 1. The whole thing in 30 seconds

```
  BUILD TIME — you, once, week 1           RUNTIME — the inspector, every scan
  (a laptop task, like any coding)         (~10 seconds, no law step at all)
  ─────────────────────────────            ──────────────────────────────
  Download 3 PDFs from the                 Inspector opens web app on phone
  government site                                    ↓
          ↓                                Takes 2–6 photos of the package
  Read the English text                              ↓
          ↓                                Photos upload to server
  Type ~12 rules into rules.yaml                     ↓
          ↓                                PaddleOCR reads all the text
  Commit to git                                      ↓
                                           Regex pulls out MRP, qty, dates…
          │                                          ↓
          └──────────────────────────────►  Rule engine runs rules.yaml
                                                     ↓
                                           Step-by-step PASS / FAIL / CAN'T TELL
                                                     ↓
                                           Saved to Postgres → dashboard + PDF
```

**The key idea:** the law is compiled into the app **before it ever reaches an
inspector** — the left column happens on your laptop in week 1 and then never again.
At runtime the app only reads `rules.yaml` off its own disk. It never downloads a PDF,
never calls the government site, and never asks the inspector anything about the law.
That is why it is fast, why it works offline, and why it keeps working when the
government site is down (which, from testing, is often).

---

## 2. Tool list

| Job | Tool | Why this one |
|---|---|---|
| Read text from photos | **PaddleOCR** (Python) | Best free OCR for English + Devanagari. One `pip install`. Gives you text **and** bounding boxes — you need the boxes for font size. |
| Backend API | **FastAPI** (Python) | OCR is Python, so the backend must be Python. Auto-generates API docs at `/docs`, which is free marks in a demo. |
| Image geometry | **OpenCV** | Crop, deskew, measure, detect the reference card. |
| Database | **PostgreSQL** (or SQLite to start) | Start on SQLite so nobody has to install anything. Switch to Postgres in week 3 if you want the dashboard charts to be fast. |
| Image storage | **A folder on disk** | Seriously. `./uploads/{scan_id}/front.jpg`. MinIO is a week-5 nicety. |
| Frontend | **React + Vite + Tailwind** | Fast to build. One codebase serves both the phone capture screen and the desktop dashboard. |
| Camera | **`navigator.mediaDevices.getUserMedia`** | Built into every browser. No app install — a judge can open your URL on their own phone. |
| Auth / RBAC | **JWT + a `role` column** | `python-jose` + a FastAPI dependency. ~40 lines. Keycloak is overkill. |
| PDF report | **WeasyPrint** | You write HTML+CSS (which you already know) and it renders a PDF. |
| Editable report | **python-docx** | Problem statement says "editable formats". `.docx` satisfies it. |
| Charts | **Recharts** | Drop-in React charts for the dashboard. |
| Running it | **Docker Compose** | One `docker compose up`. **No Kubernetes.** |

Install list:

```bash
pip install fastapi uvicorn python-multipart paddleocr paddlepaddle \
            opencv-python-headless pyyaml pydantic sqlalchemy psycopg2-binary \
            weasyprint python-docx python-jose[cryptography] passlib[bcrypt]

npm create vite@latest frontend -- --template react
npm i tailwindcss recharts axios
```

---

## 3. Build-time: baking the law into the app (week 1, on your laptop)

> ### ⚠️ Who does this: YOU, the developers. Once. Before the demo.
>
> **The inspector never uploads a law. The inspector never sees a law file.**
> `rules.yaml` is *source code* — it lives next to `main.py`, gets committed to git, and
> ships inside the app exactly like the regexes and the API routes do. Nobody uploads it,
> the same way nobody uploads `extract.py`.
>
> | Person | When | Their relationship to the law |
> |---|---|---|
> | **Dev team** | Week 1, on a laptop | Reads the PDFs, writes `rules.yaml`, commits it |
> | **Admin** (dept HQ or you) | Only when the law changes | Edits rules in an admin screen, or you ship a new version |
> | **Inspector** | Every day, in a shop | **Never touches it.** Opens app → camera → verdict |
>
> The inspector's whole world is: *login → new scan → photos → check → read result →
> download PDF.* There is no law step in that flow, and there never will be.

So: **you do it by hand, once.** No crawler. No RAG. No vector database.

### Step 1 — download three files

```bash
# NOTE: the site's TLS cert is expired, so -k is required.
# NOTE: links on the page say http:// but port 80 is dead. Use https://.

# (a) Clean consolidated English text — ALREADY IN THIS REPO:
#     docs/source-extracts/LMPC-2011-consolidated-to-2021-10-31.txt

# (b) The 2017 amendment — this is the one that changed the font table
curl -sSLk -o gsr2017.pdf \
  "https://consumeraffairs.gov.in/public/upload/files/8(xii)_0_1732871346.pdf"

# (c) The base 2011 rules, for citations and page images
curl -sSLk -o base2011.pdf \
  "https://consumeraffairs.gov.in/public/upload/files/8_1732871406.pdf"
```

### Step 2 — read the English, ignore the Hindi

`pdftotext -layout gsr2017.pdf -` gives you clean English. The Hindi comes out as
garbage (legacy font) — that is fine, you do not need it.

The base 2011 file is a **scan** with no text layer, so use it only for screenshots of
pages you want to cite.

### Step 2.5 — Why this is done by a human (and why that is not "worse")

The objection is reasonable: *hand-converting law into YAML sounds primitive. Shouldn't
the AI just read the law?*

Here is a real sentence from the Act, Rule 6(1)(c), verbatim:

> *"The net quantity, in terms of the standard unit of weight or measure, of the
> commodity contained in the package or where the commodity is packed or sold by number,
> the number of the commodity contained in the package shall be mentioned."*

To turn that into a program you must answer eight questions the sentence does not answer:

| Question | Answer in the prose |
|---|---|
| Is `gm` a standard unit? `gms`? `Gm`? `GM`? | — |
| Does `500g` (no space) comply, or must it be `500 g`? | — |
| "Mentioned" — anywhere on the pack, or on the principal display panel? | — |
| Pack shows `200g` in the recipe panel *and* `Net Wt. 200 g` on the back. Which is the declaration? | — |
| `500 g + 50 g free` — is net quantity 500 or 550? | — |
| `6 × 50 g` multipack — compliant, and what is the net? | — |
| Must "Net Wt." appear, or is a bare `200 g` enough? | — |
| `200 g ± 2%` — compliant? | — |

**The conversion is not transcription. It is adjudication.** There is no text to
translate; there is a judgment to make. That is why no tool can do it for you.

#### The decisions get made either way

This is the part that settles it. If you skip `rules.yaml` and let a model read the
label at runtime, **it still makes all eight decisions** — silently, differently on each
run, with no record. You have not avoided them. You have hidden them.

| | Decision recorded in `rules.yaml` | Decision made inside a prompt |
|---|---|---|
| Where is it written? | one line, in git, with a citation | nowhere |
| Same answer twice? | always | not guaranteed |
| Can you show a judge? | yes — point at the line | no |
| Wrong answer? | one-line fix, diffable | re-prompt and hope |
| Who is accountable? | the reviewer who signed it | nobody |

#### But do NOT type it by hand — draft it with an LLM

Hand-typing 15 rules *is* a waste of a day. Use a model as a **build-time typing
accelerator**, with a human gate:

```
1. Paste the rule text into Claude/GPT with your schema, and ask:
     "Convert this to our rules.yaml format. Then list EVERY ambiguity you
      had to resolve to do it, and what you assumed."
2. It drafts the YAML and flags e.g. "assumed 'gm' and 'gms' are acceptable
   variants of 'g'; assumed 'mentioned' means anywhere on the package".
3. You read the flags. You accept six, change two.
4. Commit.
```

About 10× faster than typing, and the eight decisions still end up **written down in a
reviewable file**, which was the whole objective.

#### The line that matters is build-time vs runtime

Not human vs AI.

| | Build time (week 1, your laptop) | Runtime (during a scan) |
|---|---|---|
| LLM drafts `rules.yaml` | ✅ reviewed, versioned, frozen before demo day | — |
| LLM suggests which token is the MRP | ✅ a human-checkable hint | ✅ allowed |
| LLM decides PASS/FAIL | — | ❌ never |
| LLM decides which rule applies | — | ❌ never |
| LLM produces the citation | — | ❌ never |

#### Scale check

This is not an endless task:

- LMPC 2011 has ~40 rules. You implement **12–15**.
- With LLM drafting: ~15 min each including review.
- **One afternoon, once.** Then it is a file that never changes unless the law does.

Legal formalisation being manual is not a hackathon shortcut — it is how regtech
actually works, because a false accusation against a real manufacturer is not an
acceptable output of a probabilistic system.

### Step 3 — type the rules into `rules.yaml`

This is a couple of hours of reading. Do not automate it. A human reading the rule and
writing it down is *more* trustworthy than an LLM doing it, and you can say so on stage.

```yaml
# backend/rules.yaml
- id: R6_MRP_PRESENT
  title: "Maximum Retail Price must be declared"
  stage: presence
  check: field_present
  params: { field: mrp }
  citation: "Rule 6(1)(e), LMPC Rules 2011"
  severity: major

- id: R6_MRP_FORMAT
  title: "MRP must be stated as inclusive of all taxes"
  stage: format
  check: text_contains_any
  params:
    field: mrp
    phrases: ["incl", "inclusive of all taxes", "incl. of all taxes"]
  citation: "Rule 6(1)(e), LMPC Rules 2011"
  severity: minor

- id: R6_NETQTY_PRESENT
  title: "Net quantity must be declared in standard units"
  stage: presence
  check: field_present
  params: { field: net_quantity }
  citation: "Rule 6(1)(c), LMPC Rules 2011"
  severity: major

- id: R6_DATE_PRESENT
  title: "Month and year of manufacture/packing must be declared"
  stage: presence
  check: field_present
  params: { field: pack_date }
  citation: "Rule 6(1)(d), LMPC Rules 2011"
  severity: major

- id: R6_CONSUMER_CARE
  title: "Consumer care details must be declared"
  stage: presence
  check: field_present
  params: { field: consumer_care }
  citation: "Rule 6(2), LMPC Rules 2011"
  severity: major

- id: R7_WIDTH_RATIO
  title: "Letter width must be at least one-third of its height"
  stage: typography
  check: width_height_ratio
  params: { min_ratio: 0.3333, fields: [mrp, net_quantity] }
  citation: "Rule 7(3), as substituted by G.S.R. 629(E) (Amendment Rules 2017)"
  severity: major

- id: R7_LETTER_HEIGHT
  title: "Minimum letter height by principal display panel area"
  stage: typography
  check: min_letter_height
  params:
    fields: [mrp, net_quantity]
    table: rule7_table_1
  citation: "Rule 7(2) & Table-I, as substituted by G.S.R. 629(E) (2017)"
  severity: major
  requires_calibration: true

- id: R8_CLEAR_SPACE
  title: "Space around the quantity declaration must be free of other print"
  stage: placement
  check: clear_space
  params:
    field: net_quantity
    above_below_multiple: 1.0
    left_right_multiple: 2.0
  citation: "Rule 8, LMPC Rules 2011"
  severity: minor

- id: R9_LANGUAGE
  title: "Declarations must be in Hindi (Devanagari) or English"
  stage: format
  check: script_in
  params: { allowed: [latin, devanagari] }
  citation: "Rule 9(4), LMPC Rules 2011"
  severity: minor
```

And the threshold table, in a separate file so it is obviously *data*, not code:

```yaml
# backend/tables.yaml
rule7_table_1:
  source: "G.S.R. 629(E), Amendment Rules 2017, page 11"
  note: "Replaced the original 2011 table. The 2011 table used NET QUANTITY. This one uses PDP AREA."
  rows:                        # area is 'A' in cm^2, upper bound inclusive
    - { max_area_cm2: 50,   normal_mm: 1.0, molded_mm: 1.5 }
    - { max_area_cm2: 100,  normal_mm: 1.5, molded_mm: 3.0 }
    - { max_area_cm2: 500,  normal_mm: 2.5, molded_mm: 4.0 }
    - { max_area_cm2: 2500, normal_mm: 4.0, molded_mm: 6.0 }
    - { max_area_cm2: null, normal_mm: 6.0, molded_mm: 6.0 }   # null = no upper bound
```

That is your entire "law database". A file in git. Reviewable, diffable, citable.

---

## 4. Runtime: what actually happens when an inspector scans (the live flow)

### What the officer does

1. Opens the web app on a phone, logs in
2. Presses **New Scan**
3. Answers two dropdowns: *package shape?* (`rectangular` / `bottle` / `pouch`) and
   *is it a food item?*
4. Takes photos — the app shows a checklist: **Front · Back · Sides · Top/Bottom**
5. For the font-size check: lays a **bank/ID card** flat next to the label and takes one
   more photo (see §6)
6. Presses **Check Compliance**
7. Watches the steps light up one by one
8. Downloads the PDF report

### What the server does

```
POST /api/scans                     → create scan, return scan_id
POST /api/scans/{id}/images         → upload one photo (repeat per surface)
POST /api/scans/{id}/run            → start the job, return immediately
GET  /api/scans/{id}/status         → frontend polls this every 1s
GET  /api/scans/{id}/report.pdf     → download
```

Inside `run`:

```
1. Load all images for the scan
2. PaddleOCR each one           → list of {text, box, confidence}
3. Regex over the text          → {mrp, net_quantity, pack_date, ...} with boxes
4. If a card was detected       → compute mm-per-pixel
5. Load rules.yaml + tables.yaml
6. For each rule: run its check function → PASS / FAIL / INDETERMINATE
7. Save everything to the DB
8. Done — status endpoint now returns the results
```

**Do not hold the HTTP request open** for all of that. Return a `scan_id` immediately
and let the frontend poll. This is what makes the step-by-step UI possible.

---

## 4.5 How comparison actually works (worked trace)

The question everyone asks: *the law is prose, the photo gives text — how do you compare
them?*

**You don't.** Prose is never compared to anything. Here is the real mechanism.

### 4.5.1 The translation happens once, in a human head

Take one requirement, Rule 6(1)(e):

> *"the retail sale price of the package shall be declared as 'Maximum Retail Price
> Rs. … inclusive of all taxes'"*

A person reads that sentence and pulls out **three separately testable assertions**:

| # | Assertion | Becomes |
|---|---|---|
| 1 | An MRP declaration exists somewhere on the pack | `field_present(mrp)` |
| 2 | It is labelled as MRP / Maximum Retail Price | regex in `extract.py` |
| 3 | It states that the price includes all taxes | `text_contains_any(mrp, ["inclusive of all taxes", …])` |

Assertions 1 and 3 become two rows in `rules.yaml`. The sentence itself becomes the
`citation:` string — **a label to print on the report, never something the code reads.**

That translation is the whole "understanding the law" step, and it is done by a student
with a PDF open, in week 1, not by a machine at scan time.

### 4.5.2 What is actually being compared

Five different mechanisms, none of which touch legal text:

| Kind of check | The comparison is literally | Example |
|---|---|---|
| **Presence** | is this key non-null in a dict? | `label["mrp"] is not None` |
| **Format** | regex / substring on a captured string | `"inclusive" in raw.lower()` |
| **Semantic** | arithmetic between extracted numbers | `abs(unit_price*qty - mrp) < 0.01` |
| **Typographic** | float comparison against a lookup table | `height_mm >= 2.5` |
| **Placement** | geometry on box coordinates | `gap_px >= 2 * numeral_height_px` |

That's it. Every verdict in the system is one of those five, evaluated on a JSON object.

---

### 4.5.3 Full trace — one photo, one packet of biscuits

**Input:** inspector photographs the front and back of a 200 g cookie pack, with a debit
card lying flat beside the front label. Types the pack size: 182 × 118 mm, rectangular.

#### Step 1 — Photos land on disk

```
uploads/a3f9c1/front.jpg     4032 × 3024
uploads/a3f9c1/back.jpg      4032 × 3024
```

#### Step 2 — PaddleOCR returns tokens (text + box)

```python
[
 {"text": "Britannia",                 "x0": 820, "y0": 310, "x1": 1740, "y1": 430, "height_px": 120, "conf": 0.99},
 {"text": "GOOD DAY",                  "x0": 700, "y0": 470, "x1": 1980, "y1": 690, "height_px": 220, "conf": 0.99},
 {"text": "Cashew Cookies",            "x0": 880, "y0": 720, "x1": 1690, "y1": 790, "height_px":  70, "conf": 0.97},
 {"text": "Net Wt. 200 g",             "x0": 910, "y0": 2180,"x1": 1310, "y1": 2214,"height_px":  34, "conf": 0.96},
 {"text": "MRP Rs. 40.00",             "x0": 905, "y0": 2260,"x1": 1073, "y1": 2281,"height_px":  21, "conf": 0.94},
 {"text": "Pkd. 08/2026",              "x0": 905, "y0": 2320,"x1": 1090, "y1": 2341,"height_px":  21, "conf": 0.92},
 {"text": "Mfd. by: Britannia Industries Ltd.", "...": "..."},
 {"text": "Bengaluru - 560038",        "...": "..."},
]
```

Nothing legal has happened yet. This is just pixels → strings + rectangles.

#### Step 3 — `extract.py` turns tokens into structured facts

Regexes run over the token texts and build one JSON object:

```python
{
  "coverage": {"complete": True},          # front AND back were captured
  "declarations": {
    "mrp":           {"raw": "MRP Rs. 40.00", "value": 40.0,
                      "tax_inclusive": False,            # ← TAX_RE did not match
                      "token": {...height_px: 21, x0: 905, x1: 1073...}},
    "net_quantity":  {"raw": "Net Wt. 200 g", "value": 200.0, "unit": "g",
                      "token": {...height_px: 34...}},
    "pack_date":     {"raw": "Pkd. 08/2026", "month": 8, "year": 2026,
                      "token": {...}},
    "consumer_care": None,                 # ← CARE_RE matched nothing anywhere
  }
}
```

**This object is the only thing the rule engine ever sees.** The photo is gone. The law
PDF was never opened.

#### Step 4 — Build the measurement context

```python
# Card found in front.jpg: long edge measured 1043 px. ISO ID-1 card = 85.60 mm.
mm_per_px = 85.60 / 1043 = 0.08207

# PDP area via Rule 7(4)(a): rectangular → height × width
pdp_area_cm2 = (182 × 118) / 100 = 214.8

ctx = {"mm_per_px": 0.08207, "mm_error_frac": 0.05,
       "pdp_area_cm2": 214.8, "is_molded": False}
```

#### Step 5 — The engine loops over `rules.yaml`

For each rule it looks up one Python function and calls it. Seven rules, seven
comparisons:

**`R6_MRP_PRESENT`** → `field_present`
```python
label["declarations"]["mrp"] is not None    # → True
```
→ **PASS** · *"Found: MRP Rs. 40.00"*

**`R6_MRP_FORMAT`** → `text_contains_any`
```python
any(p in "mrp rs. 40.00" for p in ["incl", "inclusive of all taxes"])   # → False
```
→ **FAIL** · *"\"MRP Rs. 40.00\" does not state that the price includes all taxes"*
· cite *Rule 6(1)(e)*

**`R6_NETQTY_PRESENT`** → **PASS** · *"Found: Net Wt. 200 g"*

**`R6_DATE_PRESENT`** → **PASS** · *"Found: Pkd. 08/2026"*

**`R6_CONSUMER_CARE`** → `field_present`
```python
label["declarations"]["consumer_care"] is None   # → True, so check coverage
label["coverage"]["complete"]                    # → True (front + back captured)
```
→ **FAIL** · *"No consumer care found on any photographed surface"*

> Had only the front been photographed, `coverage.complete` would be `False` and this
> becomes **INDETERMINATE** instead. Same missing field, different verdict, because the
> evidence is different. This is the single most important line of logic in the system.

**`R7_WIDTH_RATIO`** → `width_height_ratio` — *needs no calibration*
```python
token  = mrp token, text "MRP Rs. 40.00" (13 chars)
height = 21 px
width  = (1073 - 905) / 13 = 12.9 px per character
ratio  = 12.9 / 21 = 0.61      vs  required 0.333
```
→ **PASS** · *"mrp: width/height = 0.61 (minimum 0.33)"* · cite *Rule 7(3), G.S.R. 629(E) 2017*

**`R7_LETTER_HEIGHT`** → `min_letter_height` — *needs calibration*
```python
height_mm = 21 px × 0.08207 mm/px = 1.72 mm
interval  = 1.72 × (1 ∓ 0.05)     = [1.63, 1.81]

# lookup_threshold(214.8, molded=False):
#   214.8 > 50 ... > 100 ... ≤ 500  → row 3  → 2.5 mm
required = 2.5

1.81 < 2.5   →  the whole interval sits below the threshold
```
→ **FAIL** · *"mrp: measured 1.72 mm (95% range 1.63–1.81), required ≥ 2.5 mm for a PDP
area of 215 cm²"* · cite *Rule 7(2) Table-I, G.S.R. 629(E) 2017*

#### Step 6 — Roll up by stage

```python
{
  "stages": [
    {"stage": "presence",   "status": "FAIL"},   # consumer care missing
    {"stage": "format",     "status": "FAIL"},   # tax phrase missing
    {"stage": "typography", "status": "FAIL"},   # letter too small
    {"stage": "placement",  "status": "PASS"},
  ],
  "overall": "NON_COMPLIANT_PROVISIONAL"
}
```

#### Step 7 — Render

Each result carries `evidence_box`, so the UI draws the rectangle back onto the original
photo, and prints the citation next to it. That is the entire loop.

---

### 4.5.4 Where the law text actually lives

Three places, and none of them is the comparison:

| Place | Role |
|---|---|
| `rules.yaml` → `citation:` | A string printed on screen and in the PDF |
| `docs/source-extracts/*.txt` | For humans, when writing or auditing a rule |
| Page-image crop of the gazette | Optional: show the actual printed rule in the report |

If you deleted every law PDF from the machine after week 1, the app would run
identically. That is the correct property — and it is exactly why a judge asking *"what
if the government site is down?"* gets a one-word answer.

### 4.5.5 Why not just let an LLM read the law and the label together?

Because you could not answer any of these:

- Which rule did it apply? Is that rule still in force?
- Would it give the same verdict twice on the same photo?
- Can it tell "not found" from "not photographed"?
- Did it compare 1.72 against 2.5, or did it guess?

`1.72 < 2.5` is checkable by anyone in the room. That is the entire pitch.

---

## 5. The code, for real

### 5.1 Folder layout

```
sih/
├── backend/
│   ├── main.py          # FastAPI routes
│   ├── ocr.py           # PaddleOCR wrapper
│   ├── extract.py       # regex → structured fields
│   ├── checks.py        # the check functions
│   ├── engine.py        # loads rules.yaml, runs checks
│   ├── measure.py       # card detection, mm-per-pixel, glyph height
│   ├── report.py        # PDF + DOCX
│   ├── db.py            # SQLAlchemy models
│   ├── auth.py          # JWT + roles
│   ├── rules.yaml
│   └── tables.yaml
├── frontend/            # React + Vite
├── uploads/             # just a folder
├── docs/
└── docker-compose.yml
```

### 5.2 OCR wrapper — `ocr.py`

```python
from paddleocr import PaddleOCR

# Load once at startup, NOT per request (it takes ~10s to load)
_ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)

def read_image(path: str) -> list[dict]:
    """Return every text token with its box."""
    raw = _ocr.ocr(path, cls=True)
    tokens = []
    for line in (raw[0] or []):
        box, (text, conf) = line
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        tokens.append({
            "text": text,
            "conf": float(conf),
            "box": box,                                  # 4 corner points
            "x0": min(xs), "y0": min(ys),
            "x1": max(xs), "y1": max(ys),
            "height_px": max(ys) - min(ys),
        })
    return tokens
```

> Run a second pass with `lang="devanagari"` for Hindi labels and merge the token lists.

### 5.3 Extraction — `extract.py`

```python
import re

MRP_RE = re.compile(
    r"(?:M\.?R\.?P\.?|Maximum\s+Retail\s+Price)\s*[:\-]?\s*"
    r"(?:Rs\.?|₹|INR)?\s*([0-9]+(?:\.[0-9]{1,2})?)", re.I)

QTY_RE = re.compile(
    r"(?:Net\s*(?:Qty|Quantity|Wt|Weight|Vol)|Net)\s*[:\-.]?\s*"
    r"([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|mg|ml|l|ltr|litre|N)\b", re.I)

DATE_RE = re.compile(
    r"(?:MFD|MFG|PKD|Mfd|Packed\s*on|Date\s*of\s*(?:Mfg|Packing))\s*[:\-.]?\s*"
    r"([0-9]{1,2})\s*[/\-.]\s*([0-9]{2,4})", re.I)

CARE_RE = re.compile(
    r"(?:Customer|Consumer)\s*Care|Toll\s*Free|For\s+complaints", re.I)

TAX_RE = re.compile(r"incl(?:usive)?\.?\s*(?:of)?\s*all\s*taxes", re.I)


def _find(tokens, pattern):
    """Return the first token matching `pattern`, with its captured groups."""
    for t in tokens:
        m = pattern.search(t["text"])
        if m:
            return {"raw": t["text"], "groups": m.groups(), "token": t}
    return None


def extract(tokens: list[dict], coverage_complete: bool) -> dict:
    mrp  = _find(tokens, MRP_RE)
    qty  = _find(tokens, QTY_RE)
    date = _find(tokens, DATE_RE)
    care = _find(tokens, CARE_RE)

    return {
        "coverage": {"complete": coverage_complete},
        "declarations": {
            "mrp": None if not mrp else {
                "raw": mrp["raw"],
                "value": float(mrp["groups"][0]),
                "tax_inclusive": bool(TAX_RE.search(mrp["raw"])),
                "token": mrp["token"],
            },
            "net_quantity": None if not qty else {
                "raw": qty["raw"],
                "value": float(qty["groups"][0]),
                "unit": qty["groups"][1].lower(),
                "token": qty["token"],
            },
            "pack_date": None if not date else {
                "raw": date["raw"],
                "month": int(date["groups"][0]),
                "year": int(date["groups"][1]),
                "token": date["token"],
            },
            "consumer_care": None if not care else {
                "raw": care["raw"], "token": care["token"],
            },
        },
        "all_tokens": tokens,
    }
```

That is genuinely most of the extraction problem for a hackathon. Regex over OCR text
gets you surprisingly far. Add a vision-model fallback later **only** if you have time.

### 5.4 The check functions — `checks.py`

```python
CHECKS = {}

def check(name):
    def deco(fn):
        CHECKS[name] = fn
        return fn
    return deco


@check("field_present")
def field_present(label, p, ctx):
    f = label["declarations"].get(p["field"])
    if f:
        return "PASS", f"Found: \"{f['raw']}\"", f["token"]
    if not label["coverage"]["complete"]:
        return "INDETERMINATE", \
               "Not every package surface was photographed, so absence cannot be confirmed", None
    return "FAIL", f"No {p['field'].replace('_',' ')} found on any photographed surface", None


@check("text_contains_any")
def text_contains_any(label, p, ctx):
    f = label["declarations"].get(p["field"])
    if not f:
        return "INDETERMINATE", "Field not found, so its format cannot be checked", None
    low = f["raw"].lower()
    if any(ph.lower() in low for ph in p["phrases"]):
        return "PASS", f"Declaration reads \"{f['raw']}\"", f["token"]
    return "FAIL", f"\"{f['raw']}\" does not state that the price includes all taxes", f["token"]


@check("width_height_ratio")
def width_height_ratio(label, p, ctx):
    """Rule 7(3). Pure pixel ratio — needs NO calibration."""
    worst = None
    for name in p["fields"]:
        f = label["declarations"].get(name)
        if not f:
            continue
        t = f["token"]
        h = t["height_px"]
        w = (t["x1"] - t["x0"]) / max(len(t["text"]), 1)   # mean per-character width
        ratio = w / h if h else 0
        if worst is None or ratio < worst[0]:
            worst = (ratio, name, t)
    if worst is None:
        return "INDETERMINATE", "No measurable declaration found", None
    ratio, name, tok = worst
    if ratio >= p["min_ratio"]:
        return "PASS", f"{name}: width/height = {ratio:.2f} (minimum 0.33)", tok
    return "FAIL", f"{name}: width/height = {ratio:.2f}, below the required 0.33", tok


@check("min_letter_height")
def min_letter_height(label, p, ctx):
    """Rule 7(2) Table-I. NEEDS calibration (mm per pixel)."""
    if not ctx.get("mm_per_px"):
        return "INDETERMINATE", \
               "No reference object in the photo, so millimetres cannot be measured", None
    if not ctx.get("pdp_area_cm2"):
        return "INDETERMINATE", "Package dimensions unknown, so the PDP area is unknown", None

    required = lookup_threshold(ctx["pdp_area_cm2"], ctx["is_molded"], ctx["table"])
    worst = None
    for name in p["fields"]:
        f = label["declarations"].get(name)
        if not f:
            continue
        h_mm = f["token"]["height_px"] * ctx["mm_per_px"]
        err  = ctx["mm_error_frac"]                     # e.g. 0.05 for +/-5%
        lo, hi = h_mm * (1 - err), h_mm * (1 + err)
        if worst is None or lo < worst[0]:
            worst = (lo, hi, h_mm, name, f["token"])

    if worst is None:
        return "INDETERMINATE", "No measurable declaration found", None
    lo, hi, h_mm, name, tok = worst

    detail = (f"{name}: measured {h_mm:.2f} mm (95% range {lo:.2f}–{hi:.2f}), "
              f"required ≥ {required} mm for a PDP area of {ctx['pdp_area_cm2']:.0f} cm²")
    if lo >= required:
        return "PASS", detail, tok
    if hi <  required:
        return "FAIL", detail, tok
    return "INDETERMINATE", detail + " — the measurement straddles the threshold", tok


def lookup_threshold(area_cm2, is_molded, table):
    for row in table["rows"]:
        if row["max_area_cm2"] is None or area_cm2 <= row["max_area_cm2"]:
            return row["molded_mm"] if is_molded else row["normal_mm"]
```

Notice what these functions have in common: **plain Python, no model, no LLM.** Anyone
can read one and check it against the rule. That is the whole argument.

### 5.5 The engine — `engine.py`

```python
import yaml
from checks import CHECKS

RULES  = yaml.safe_load(open("rules.yaml"))
TABLES = yaml.safe_load(open("tables.yaml"))

STAGES = ["presence", "format", "semantic", "typography", "placement"]


def evaluate(label: dict, ctx: dict) -> dict:
    ctx = {**ctx, "table": TABLES["rule7_table_1"]}
    results = []
    for rule in RULES:
        fn = CHECKS[rule["check"]]
        try:
            status, reason, token = fn(label, rule.get("params", {}), ctx)
        except Exception as e:
            status, reason, token = "SYSTEM_ERROR", f"Check crashed: {e}", None
        results.append({
            "rule_id":  rule["id"],
            "title":    rule["title"],
            "stage":    rule["stage"],
            "status":   status,
            "reason":   reason,
            "citation": rule["citation"],
            "severity": rule["severity"],
            "evidence_box": token["box"] if token else None,
        })

    by_stage = {s: [r for r in results if r["stage"] == s] for s in STAGES}
    return {
        "results": results,
        "stages": [
            {"stage": s,
             "status": roll_up([r["status"] for r in by_stage[s]])}
            for s in STAGES if by_stage[s]
        ],
        "overall": overall_status(results),
    }


def roll_up(statuses):
    if "FAIL" in statuses:          return "FAIL"
    if "INDETERMINATE" in statuses: return "INDETERMINATE"
    if "SYSTEM_ERROR" in statuses:  return "SYSTEM_ERROR"
    return "PASS"


def overall_status(results):
    if any(r["status"] == "FAIL" for r in results):
        return "NON_COMPLIANT_PROVISIONAL"
    if any(r["status"] == "INDETERMINATE" for r in results):
        return "INCOMPLETE_ASSESSMENT"
    return "COMPLIANT_WITHIN_SCOPE"     # never plain "COMPLIANT"
```

`stages` is exactly the step-1 / step-2 pass-fail list from the original plan.

### 5.6 API — `main.py`

```python
import uuid, shutil, os
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, Depends
from ocr import read_image
from extract import extract
from engine import evaluate
from measure import calibrate_from_card, pdp_area_cm2
from auth import current_user, require_role

app = FastAPI(title="Legal Metrology Compliance Checker")
JOBS = {}          # scan_id -> dict. Redis in week 5; a dict is fine now.


@app.post("/api/scans")
def create_scan(shape: str = Form(...), is_food: bool = Form(False),
                user=Depends(current_user)):
    sid = str(uuid.uuid4())[:8]
    os.makedirs(f"uploads/{sid}", exist_ok=True)
    JOBS[sid] = {"status": "collecting", "shape": shape, "is_food": is_food,
                 "officer": user["sub"], "images": []}
    return {"scan_id": sid}


@app.post("/api/scans/{sid}/images")
def add_image(sid: str, surface: str = Form(...), file: UploadFile = File(...)):
    path = f"uploads/{sid}/{surface}.jpg"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    JOBS[sid]["images"].append({"surface": surface, "path": path})
    return {"ok": True, "captured": [i["surface"] for i in JOBS[sid]["images"]]}


@app.post("/api/scans/{sid}/run")
def run_scan(sid: str, bg: BackgroundTasks,
             height_mm: float = Form(None), width_mm: float = Form(None)):
    JOBS[sid]["status"] = "running"
    bg.add_task(_process, sid, height_mm, width_mm)
    return {"scan_id": sid, "status": "running"}


def _process(sid, height_mm, width_mm):
    job = JOBS[sid]
    try:
        tokens = []
        for img in job["images"]:
            tokens += read_image(img["path"])

        required = {"front", "back"}
        complete = required <= {i["surface"] for i in job["images"]}

        label = extract(tokens, coverage_complete=complete)

        mm_per_px, err = calibrate_from_card(job["images"][0]["path"])
        ctx = {
            "mm_per_px": mm_per_px,
            "mm_error_frac": err,
            "pdp_area_cm2": pdp_area_cm2(job["shape"], height_mm, width_mm),
            "is_molded": False,
        }

        job["result"] = evaluate(label, ctx)
        job["label"]  = label
        job["status"] = "done"
    except Exception as e:
        job["status"], job["error"] = "error", str(e)


@app.get("/api/scans/{sid}/status")
def status(sid: str):
    j = JOBS[sid]
    return {"status": j["status"], "result": j.get("result"), "error": j.get("error")}


@app.get("/api/scans")
def list_scans(user=Depends(require_role("officer", "supervisor"))):
    return [{"scan_id": k, "status": v["status"],
             "overall": v.get("result", {}).get("overall")} for k, v in JOBS.items()]
```

### 5.7 Auth — `auth.py` (the whole of RBAC)

```python
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt

SECRET, ALGO = "change-me", "HS256"
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/login")

def current_user(token: str = Depends(oauth2)):
    try:
        return jwt.decode(token, SECRET, algorithms=[ALGO])   # {"sub":..., "role":...}
    except Exception:
        raise HTTPException(401, "Invalid token")

def require_role(*roles):
    def dep(user=Depends(current_user)):
        if user.get("role") not in roles:
            raise HTTPException(403, f"Requires one of: {roles}")
        return user
    return dep
```

Roles: `officer` (scan, view own) · `supervisor` (view all, confirm violations) ·
`admin` (manage users and rules). That satisfies "role-based access" for a hackathon.

---

## 6. Measuring millimetres without lab equipment

The threshold depends on real-world size, but a photo has no scale. Two answers, and
you should build them in this order.

### 6.1 Free checks (build first, week 3) — no calibration at all

- **Rule 7(3)** width ≥ ⅓ height → a ratio of two pixel measurements
- **Rule 8** clear space ≥ 1× / 2× numeral height → a ratio of two pixel measurements

Both work on **any photo you already have**. Real violations, zero uncertainty. These
alone give you a working typography feature.

### 6.2 Absolute mm (week 4) — use a bank card

Every officer has an ID-1 card (debit card, Aadhaar, PAN). ISO/IEC 7810 fixes it at
**85.60 × 53.98 mm**. Lay it flat beside the label, in the same photo.

```python
# measure.py
import cv2, numpy as np

CARD_LONG_MM = 85.60

def calibrate_from_card(path):
    """Find a card-shaped rectangle, return (mm_per_px, relative_error)."""
    img  = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:10]:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) != 4:
            continue
        pts = approx.reshape(4, 2).astype("float32")
        (w, h) = _side_lengths(pts)
        long_px, short_px = max(w, h), min(w, h)
        if not (1.5 < long_px / short_px < 1.75):     # card aspect is 1.586
            continue
        return CARD_LONG_MM / long_px, 0.05            # ~5% is honest for this method

    return None, None                                  # no card -> INDETERMINATE


def pdp_area_cm2(shape, height_mm, width_mm):
    """Rule 7(4). Officer types the two dimensions; we apply the legal formula."""
    if not height_mm or not width_mm:
        return None
    if shape == "rectangular":
        return (height_mm * width_mm) / 100.0                    # 7(4)(a)
    if shape in ("bottle", "cylindrical"):
        circumference = 3.14159 * width_mm                       # width = diameter
        return 0.40 * (height_mm * circumference) / 100.0        # 7(4)(b)
    return 0.40 * (height_mm * width_mm) / 100.0                 # 7(4)(c)
```

**Always show the interval and the method**, never a bare number:

> Measured **2.18 mm** (95% range 2.07 – 2.29) · method: ID-1 card reference
> Required ≥ **2.5 mm** · PDP area 214 cm² → **FAIL**

If no card is in the photo, the answer is `INDETERMINATE` — not a guess. Being able to
say "we refuse to guess" is a scoring point, not a weakness.

---

## 7. What the screen looks like

### Scan result

```
┌──────────────────────────────────────────────────────────┐
│  Scan #a3f9c1        Britannia Good Day 200g             │
│  Overall: NON-COMPLIANT (provisional — needs officer OK) │
├──────────────────────────────────────────────────────────┤
│  ✅  Step 1  Applicability        Covered by LMPC 2011   │
│  ✅  Step 2  Evidence             6 of 6 surfaces        │
│  ✅  Step 3  Presence             5 of 5 declarations    │
│  ❌  Step 4  Format               1 issue                │
│  ✅  Step 5  Semantics            consistent             │
│  ❌  Step 6  Typography           1 issue                │
│  ⚠️  Step 7  Placement            cannot determine       │
├──────────────────────────────────────────────────────────┤
│  ❌ MRP must state "inclusive of all taxes"              │
│     Found: "MRP Rs. 40.00"                               │
│     Rule 6(1)(e), LMPC Rules 2011          [see evidence]│
│                                                           │
│  ❌ Minimum letter height                                 │
│     Measured 1.72 mm (95% range 1.63–1.81)               │
│     Required ≥ 2.5 mm  ·  PDP area 214 cm²               │
│     Rule 7(2) Table-I, G.S.R. 629(E) 2017  [see evidence]│
│                                                           │
│  ⚠️ Clear space around net quantity                      │
│     Left edge of the panel was cut off in the photo      │
│     Rule 8, LMPC Rules 2011                              │
├──────────────────────────────────────────────────────────┤
│  [ Confirm violations ]  [ Download PDF ]  [ DOCX ]      │
└──────────────────────────────────────────────────────────┘
```

`[see evidence]` opens the photo with the box drawn on it. That single feature does more
for credibility than any accuracy number.

### Dashboard

Four tiles (scans today · violations found · pending review · avg. per scan), a bar
chart of *violations by rule*, a bar chart of *violations by brand*, and a searchable
table with filters on date / status / rule / officer. Recharts + a plain table.

---

## 8. Reports

```python
# report.py
from weasyprint import HTML
from docx import Document

def make_pdf(scan, out):
    html = render_template("report.html", scan=scan)   # jinja2
    HTML(string=html, base_url=".").write_pdf(out)

def make_docx(scan, out):
    d = Document()
    d.add_heading("Legal Metrology Compliance Report", 0)
    d.add_paragraph(f"Scan ID: {scan['id']}    Date: {scan['date']}")
    d.add_paragraph(f"Officer: {scan['officer']}")
    d.add_heading("Findings", level=1)
    t = d.add_table(rows=1, cols=4); t.style = "Light Grid Accent 1"
    for i, h in enumerate(["Rule", "Status", "Reason", "Citation"]):
        t.rows[0].cells[i].text = h
    for r in scan["results"]:
        c = t.add_row().cells
        c[0].text, c[1].text = r["title"], r["status"]
        c[2].text, c[3].text = r["reason"], r["citation"]
    for img in scan["evidence_images"]:
        d.add_picture(img, width=Inches(4))
    d.save(out)
```

Put the evidence crops in both. "Attachment of photographs and supporting evidence" is
an explicit requirement in the problem statement.

---

## 9. Who builds what

| Person | Owns |
|---|---|
| 1 | `rules.yaml` + `checks.py` + `engine.py` — **the legal core** |
| 2 | `ocr.py` + `extract.py` — perception |
| 3 | `measure.py` + evidence overlays — the font-size feature |
| 4 | React capture screen + result screen |
| 5 | Dashboard, auth, reports |
| 6 | Gold test set, eval script, demo rehearsal |

Person 1's work is the differentiator. If you have your strongest person, put them there
— not on the frontend.

---

## 10. Week by week

| Week | Ship |
|---|---|
| **1** | `rules.yaml` with 12 rules, all cited. `checks.py` with fake input. Tests pass. **No UI yet.** |
| **2** | Upload a photo → PaddleOCR → see tokens with boxes drawn. Regex finds MRP and quantity. |
| **3** | Full pipeline end to end. Step-by-step result screen. The two calibration-free typography checks. |
| **4** | Card calibration + mm measurement. PDF/DOCX. Login and roles. Dashboard. |
| **5** | 30+ real packages tested. Fix the top 3 failures. Offline drill. Rehearse the demo 5 times. |

**Freeze the code the night before.** Every year, teams break their demo with a last
commit.

---

## 11. Demo script (4 minutes)

1. **(20s)** "Inspectors check labels by hand. We automate the checkable parts — and we
   are explicit about what a photograph cannot prove."
2. **(60s)** Scan a real packet live. Show the steps lighting up. Land on a genuine
   violation with the evidence box drawn on the photo.
3. **(45s)** **The killer slide.** Side by side: page 47 of the 2011 PDF showing the old
   net-quantity table, and the 2017 gazette that replaced it with the PDP-area table.
   "Anyone who built this from the rules PDF on the government website is checking
   against repealed law. Every rule in our system carries an effective date and a
   citation to a gazette page."
4. **(40s)** Scan a package with the back hidden. It says **CANNOT DETERMINE**, not
   "compliant". "We never accuse a manufacturer on incomplete evidence."
5. **(45s)** Dashboard, search history, download the PDF, open the DOCX to show it is
   editable.
6. **(30s)** "The law is a reviewed YAML file in git, not a PDF we ask a model to read at
   runtime. Every verdict is plain Python you can read and check."

Point 3 is the one that wins. You have the exhibit already:
`docs/source-extracts/base-2011-p47-OLD-table-I.png`.

---

## 12. Skip all of this

Blockchain · Kubernetes · training your own OCR model · an end-to-end "compliant/
non-compliant" CNN · a vector DB · RAG at scan time · microservices · Elasticsearch ·
Redis in week 1 · a native mobile app · real-time websockets · 3D scanning ·
Hindi legal-text translation (the English is right there in the same PDF).

Every one of these costs days and adds nothing a judge will reward.
