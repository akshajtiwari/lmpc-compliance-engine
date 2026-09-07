# System Map — How It All Fits Together

For the team. What the pieces are, how they connect, and how work moves through them.
Fifteen minutes. Details live in `02-BUILD-SPEC.md`.

---

## 1. The whole system in one picture

There are **two separate machines** here, and confusing them is the most common mistake.

```
   ══════════ BUILT ONCE, OFFLINE ══════════   │   ═══ RUNS EVERY SCAN ═══
                                               │
   gazette PDFs                                │   photos of a packet
        ↓                                      │        ↓
   LAW COMPILER                                │   OCR  (read the text)
   read · order · parse · cross-check          │        ↓
        ↓                                      │   LAYOUT  (glue the pieces)
   a human approves a diff                     │        ↓
        ↓                                      │   SCORING  (which is the MRP?)
   ┌──────────────────────┐                    │        ↓
   │  RULEPACK            │ ───────────────────┼──▶ RULE ENGINE
   │  21 checks, 4 gates  │                    │        ↓
   │  versioned + hashed  │                    │   verdicts + evidence
   └──────────────────────┘                    │        ↓
                                               │   report · repository
```

**Left side** runs on a laptop, when the law changes. Weeks apart.
**Right side** runs on a server, every time an officer takes a photo. Seconds.

The rulepack is the only thing that crosses. It is a few kilobytes of numbers and
patterns — **no PDF, no website, no search ever happens during a scan.**

---

## 2. The pieces

### Left side — the law compiler (`lmpc/lawc/`)

| File | Job |
|---|---|
| `fetch.sh`, `fetch-general.sh` | Download gazette notifications from the government site |
| `parse.py` | Read them: identify each one, put them in order, extract the changes and the tables |
| `bindings.yaml` | **The human part.** Points each legal rule at a checker and records what a reviewer confirmed |
| `gaps.yaml` | Records any notification we could not obtain, who looked for it, and why it is safe |
| `build.py` | Assembles the rulepack, cross-checks it, hashes it — **or refuses to build** |

### Right side — the engine (`lmpc/engine/`)

| File | Job |
|---|---|
| `ocr.py` | Turn a photo into text with positions. Shrinks huge photos first |
| `layout.py` | Glue text pieces that sit on the same line back together |
| `lexicon.py` | Match messy headings — `MR.P` is `MRP` |
| `extract.py` | Score every candidate and pick the MRP, the weight, the date… |
| `normalize.py` | `"Rs.45.00"` → `45.00` · `"500gm"` → `500 g` · `"02/2025"` → Feb 2025 |
| `operators.py` | The twelve checkers. Plain code — this is where verdicts come from |
| `engine.py` | Runs the gates, then the checks, in the right order |
| `report.py` | Prints the result the way an officer must see it |

### Supporting

| Folder | Job |
|---|---|
| `lmpc/labels/` | Make fake labels with known answers · fetch real product photos |
| `stress/` | The test suites — scenarios, noise, real photos, resolution |
| `tests/` | Unit tests and fail-tests |
| `rulepack/` | The built rulepack |
| `docs/` | These documents |

---

## 3. How one scan flows

```
1. Officer photographs each side.  App checks blur, glare, angle BEFORE accepting.
2. App confirms every side was done  →  sets "coverage asserted"
3. Upload.  Originals stored unchanged, with a fingerprint.
4. OCR reads each photo → text pieces with positions and confidence
5. Layout glues same-line pieces together        ("NET WEIGHT :" + "220")
6. Scoring picks the MRP, weight, date, address, care details
7. Normalise into comparable values
8. RULE ENGINE:
      gates      → does this law even apply to this packet?
      temporal   → which version of the law was in force that day?
      checks     → run the 21 checks
9. Six possible answers per check, each with evidence and a gazette citation
10. Officer reviews, corrects, approves  →  PDF + Word report  →  repository
```

Step 2 is the one people skip and the one that matters most. See §5.

Full detail: [`04-FLOW.md`](04-FLOW.md).

---

## 4. How one amendment flows

```
new notification appears
    ↓
watcher finds it → QUARANTINE  (nothing is live yet)
    ↓
compiler:  identify (number + YEAR) → check the chain is unbroken
           → parse "rule 7, Table-I, substitute" → pull out the new numbers
    ↓
a person reads a before/after diff and clicks Approve
    ↓
new rulepack version + new hash → deployed
```

**Nobody types the law in.** Rules point at an *address* (`rule 7 → Table-I`), not at
numbers, so when numbers change they simply reload.

**The old table is kept, not deleted.** A packet inspected in 2017 is still judged by
2017's rule.

Setup: one day, once. Each amendment after that: a few minutes.

---

## 5. The four rules that shape the design

Everything unusual in this system exists because of one of these. Each was learned by
getting it wrong first.

**"Cannot tell" is a real answer.** Six outcomes, not two. *"We could not find the MRP"*
and *"the MRP is missing"* are different findings.

**We may only say something is missing if we looked properly.** The camera app has to
confirm it photographed every side. Until it does, every answer is "cannot tell". This is
enforced in code — the engine physically cannot issue a violation without it. *On 48 of 60
real products, the price was simply not in the photo.*

**Judge by the law of the day.** Every scan carries the date it was taken. A rule change in
2018 does not rewrite a finding from 2016.

**If the measurement cannot support the claim, refuse.** Different claims need different
certainty: *"there is text here"* survives a misread letter; *"this character is wrong,
therefore it breaks the rule"* does not.

---

## 5.5 Why it is not all inside the phone app

A fair question, and the problem statement answers it. It asks for a **repository** of
scanned products, **dashboards** for officials, **search** over previous inspections,
**role-based access**, and a "**web** and/or mobile" application. None of those exist on
one isolated handset — roles mean nothing without a central authority, and a repository
spanning officers is by definition shared.

Two more reasons of our own: a verdict computed on a device nobody controls is not
defensible evidence, and if the rules lived on phones then every amendment would need a
fleet-wide app update — with old handsets quietly applying repealed law.

**The phone still does plenty, and still works offline:** it guides the capture, rejects
bad photos, asserts coverage, queues scans with no signal, and syncs later. It holds no
thresholds, no comparisons and no rule text.

**And "server" does not mean cloud.** The whole stack runs on one departmental machine
with `docker compose up`.

---

## 6. What is NOT in the system

| Not here | Why |
|---|---|
| An AI chatbot / LLM | The problem statement asks for **rule-based** checking. Verdicts come from readable Python |
| PDFs at scan time | The app could pick up a repealed or draft rule and accuse someone |
| A "compliant / not compliant" image classifier | Cannot be explained to a magistrate |
| Kubernetes, blockchain, Elasticsearch | Not needed at this scale |

We do use AI for exactly one thing: **reading text out of a photo**. That is a camera
problem, not a legal one.

---

## 7. Who builds what

| Area | Work | Depends on |
|---|---|---|
| **Camera app** | Guided capture, quality gates, coverage confirmation, offline queue | nothing — start now |
| **Reading** | Better line assembly, bigger lexicon, Hindi | the OCR contract only |
| **Measurement** | Bank-card scale reference, panel area, letter segmentation | reading |
| **Law compiler** | Close the last loose ends | already working |
| **Console** | Review screen, corrections, dashboards, logins | the verdict format |
| **Reports** | PDF and Word from one result object | the verdict format |

The camera app is the critical path. Until it confirms coverage, the system cannot report
a violation at all — by design.

---

## 8. One thing to remember

> The system's job is not to be clever. It is to be **checkable**.
>
> Every verdict must show: what it measured, what the law required, which gazette page
> says so, and which version of the rulebook was used. If a finding cannot survive
> someone asking *"how do you know?"*, it should not be a finding.
