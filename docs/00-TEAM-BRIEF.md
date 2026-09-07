# Team Brief — Read This First

**What we are building:** an app that takes photos of a packaged product and checks
whether its label follows Indian packaging law — the Legal Metrology (Packaged
Commodities) Rules, 2011.

This page is deliberately short and plain. The details are in the other documents.

---

## 1. In one sentence

> We photograph a package, read the text off it, and compare what we found against a
> list of legal rules we wrote down by hand — and when we are not sure, we say so
> instead of guessing.

**What we are NOT building:** an AI that looks at a package and announces "legal" or
"illegal". That claim falls apart the first time a judge asks *"how do you know?"*

---

## 2. Six things everyone needs to understand

### (a) We do not read the law while the app is running

The law is a set of government PDFs. We do **not** let the app open them during a scan.

Instead, in Week 1, two people sit down, read the law, and type it into a small file
called `rules.yaml`. That file is the only thing the app ever uses.

Why: if the app went looking for the law by itself, it could easily pick up an old
version, a Hindi copy, or a draft that never became law — and then accuse a shopkeeper
of a violation based on a rule that does not exist. We cannot ship that.

### (b) The law on the government website is out of date — and that is our best demo

The 2011 rules PDF says the minimum letter size on a package depends on **how much is
inside** (1 mm / 2 mm / 4 mm).

**That was cancelled in 2017.** The rule now depends on **how big the front of the pack
is**:

| Size of the front panel | Minimum letter height | If the letters are moulded into plastic |
|---|---|---|
| under 50 cm² | 1.0 mm | 1.5 mm |
| 50 – 100 cm² | 1.5 mm | 3.0 mm |
| 100 – 500 cm² | 2.5 mm | 4.0 mm |
| 500 – 2500 cm² | 4.0 mm | 6.0 mm |
| over 2500 cm² | 6.0 mm | 6.0 mm |

If we had built from the obvious PDF, our headline feature would be checking against a
**cancelled rule**. So every rule we write carries a date and a page reference saying
exactly where it came from.

### (c) "Pass" and "fail" are not enough — we use six answers

| Answer | Meaning |
|---|---|
| `PASS` | The label follows the rule |
| `FAIL` | The label breaks the rule |
| `INDETERMINATE` | We honestly cannot tell — photo too blurry, or that side was never photographed |
| `NOT_APPLICABLE` | This rule does not apply to this product at all |
| `REVIEW_REQUIRED` | A person needs to look at this |
| `SYSTEM_ERROR` | Our bug, not the label's problem |

**The important one:** *"we could not find the MRP"* is **not** the same as *"the MRP is
missing."* If nobody photographed the back of the pack, the correct answer is
`INDETERMINATE`. Getting this right matters more than any accuracy percentage.

### (d) There is no AI chatbot in this system

The problem statement asks for **rule-based checking**, and that is exactly what we
build. No LLM, no ChatGPT-style model, anywhere in the app.

We do use AI for one thing only: **reading text out of a photo** (OCR). That is a camera
problem, not a legal one.

Everything else is ordinary Python code that a person can read line by line:

| Job | How we do it, without an LLM |
|---|---|
| Deciding which text block is the MRP | Keyword matching that tolerates spelling mistakes, plus a points system based on where the text sits |
| Understanding a smudged heading like `MR.P` | Compare it letter-by-letter against a list of known spellings |
| Writing the finding in plain language | Fill-in-the-blank sentence templates |
| Finding which documents changed Rule 6 | A database query |

If two candidates score too close together, we do not pick one. We return
`INDETERMINATE` and let an officer decide.

Why this matters: in court, you have to explain how you reached a conclusion. We can
point at ten lines of code and a page of the government gazette. "The model said so" is
not an answer.

### (e) Two size checks need no measuring equipment — build these first

Some rules are about **ratios**, not real-world millimetres:

- **Rule 7(3):** a letter's width must be at least ⅓ of its height.
- **Rule 8:** the empty space around the quantity ("500 g") must be at least 1× the
  number's height above and below, and 2× on the left and right.

These work on **any photo we already have**. No ruler, no reference card, no maths about
distance. They are real violations and they are easy. Build them first.

Measuring actual millimetres (by putting a bank card in the photo for scale) comes later.

### (f) We must know when a rule does not apply

Some packages are simply outside the law:

- More than 25 kg or 25 litres
- Cement, fertiliser or farm produce in bags over 50 kg
- Anything sold to factories or institutions rather than shoppers
- Small packs of 10 g or 10 ml or less (except tobacco)
- Restaurant and hotel takeaway food

We check these **first**, before checking anything else. If we skip this, the app will
accuse a legally exempt package of breaking rules it was never subject to.

---

## 3. What we are building

**One backend. Two screens.**

```
   Phone app (in the browser)          Officer's web console
   - guided photo taking               - review and fix mistakes
   - rejects blurry photos             - search past inspections
   - reads barcodes                    - manage rule versions
   - shows results live                - export PDF / Word reports
             \                            /
              \                          /
             ONE SERVER + THE RULE ENGINE
```

The officer's console is **not** just charts. It is where officers correct wrong
readings and approve findings. Treat it as a workbench, not a dashboard.

---

## 4. What happens when someone scans a package

```
1. Does this law even apply?          → PASS / NOT_APPLICABLE
2. Did we photograph every side?      → PASS / INDETERMINATE
3. Are all required declarations there? → PASS / FAIL / INDETERMINATE
4. Are MRP, date and quantity written correctly? → PASS / FAIL
5. Do the values make sense together? → PASS / FAIL / REVIEW
6. Are the letters big enough?        → PASS / FAIL / INDETERMINATE
7. Are they in the right place, with enough space? → PASS / FAIL
```

Steps 1 and 2 are the ones most teams forget. They are what stop us from making false
accusations.

---

## 5. The tools we use

| Part | Tool | In plain words |
|---|---|---|
| Phone app | PWA (a website that uses the camera) | Works on any phone, no app store |
| Server | FastAPI (Python) | One program, not twenty microservices |
| Reading text from photos | PaddleOCR | Handles English and Hindi |
| Image maths | OpenCV | Straightens photos, measures letters |
| Word matching | rapidfuzz | Matches `MR.P` to `MRP` despite typos |
| Database | PostgreSQL | Stores scans, results, history |
| File storage | MinIO | Stores the original photos, unchanged |
| Background jobs | Redis + Dramatiq | So the app does not freeze during OCR |
| Login and roles | Keycloak | Who can see and approve what |
| Reports | WeasyPrint + docxtpl | PDF and Word versions |
| Running it | Docker Compose | **No Kubernetes** |

---

## 6. Do not add these

Blockchain · Kubernetes · training our own OCR model from scratch · an AI that outputs
"compliant / non-compliant" directly · any chatbot or LLM in the app · Elasticsearch ·
3D scanning of packages · trying to cover every single rule and exception · a native iOS
app · publishing rule changes without a human approving them.

If someone proposes one of these, point at this list.

---

## 7. Build order

| Week | What gets finished |
|---|---|
| 1 | Write 12–14 rules by hand, with dates and page references, plus test cases |
| 2 | Photo capture + reading text from photos + showing what was found |
| 3 | Pulling out MRP, quantity, dates, address — and the six-answer result screen |
| 4 | Letter-size checks, PDF/Word reports, officer correction screen |
| 5 | Testing, tricky edge cases, offline practice run, demo rehearsal |

**Freeze everything before the finale.** Spend the last days making it reliable, not
swapping models.

---

## 8. The moment that wins the demo

Show one result card:

> **Rule 7(2) — Minimum letter height: FAIL**
> We measured 1.72 mm (could be between 1.64 and 1.80). The law requires at least 2.5 mm.
> Front panel area: 214 cm² (18.2 × 11.8 cm).
> Source: G.S.R. 629(E), Amendment Rules 2017, rule 7, Table-I, page 11.
> Rulebook version `lmpc-2026.05.29-r1`
> *[zoomed-in crop of the actual letters we measured]*

Then open the rules admin screen and show a **new 2026 government notification waiting
for a human to approve it**.

That one screen answers four questions at once: *Is this current law? How did you measure
that? Can you prove it? What happens when the law changes?*
