# What Runs Where — The Phone, The Server, and the Tech Stack

Plain English. For anyone who assumed the whole thing lives inside a phone app.

---

## 1. The short answer

There are two halves.

```
   THE PHONE                          THE SERVER
   ─────────                          ──────────
   takes the photos                   reads the text from the photos
   checks they are sharp              works out which text is the MRP
   confirms every side was shot       compares it against the law
   works with no signal               stores everything
   shows the result                   makes the reports
                                      runs the dashboards
                                      handles logins and roles
```

The phone is the **camera and the screen**. The server is **everything else**.

**Important:** "server" does not mean cloud. It can be one computer sitting in the
department's own office. `docker compose up` and it runs.

---

## 2. Why it cannot all be in the phone app

This is not a preference. The problem statement asks for six things that a single phone
cannot do.

| The problem statement asks for | Why one phone cannot do it |
|---|---|
| A **web** application | A website has to be served from somewhere |
| A **repository** of scanned products and history | Officer A's phone cannot hold Officer B's inspections |
| **Dashboards** for enforcement officials | Needs to add up work across many officers |
| **Search** of previously scanned products | Needs one shared store to search |
| **Role-based access** and secure login | A role stored on a phone is just the phone saying so. Anyone could change it |
| A documented **deployment framework** | They are explicitly asking how it gets deployed |

Three more reasons of our own:

**Evidence has to be out of reach.** A violation decided on a phone that the officer
carries into a shop is not strong evidence. Photos are fingerprinted the moment they reach
the server and can never be changed after that.

**Rules must update everywhere at once.** When the law changes, one person approves it and
every officer is using the new rules the same day. If the rules lived on phones, you would
need every officer to update their app — and until they did, they would be enforcing
**repealed law**. That is the exact mistake this whole project exists to avoid.

**Old reports must still make sense.** A report from 18 months ago has to be reproducible
exactly. That needs one controlled setup, not whatever version happened to be on someone's
handset.

---

## 3. What the phone still does — and it is a lot

The phone app is the **most important thing left to build**, because nothing produces a
finding without it.

| The phone does | Why it matters |
|---|---|
| Guides the officer through each side of the pack | On 48 of 60 real products we tested, the price was simply never photographed |
| Rejects blurry, glared, badly-angled photos **before** upload | Telling someone their photo was bad after they left the shop is useless |
| Confirms every required side was photographed | Without this confirmation the system is **not allowed** to say a declaration is missing |
| Works with no internet | Scans queue on the phone and upload when signal returns |
| Shows results and lets the officer add notes | |

**What the phone does not have:** any rule, any threshold, any legal text. It never decides
anything. If the law changes, the phone app does not change.

---

## 4. The server, explained

### 4.1 The pieces

```
                    ┌──────────┐
   phone / browser ─┤   API    ├─ handles requests, checks who you are
                    └────┬─────┘
                         │ puts jobs on a queue
                    ┌────▼─────┐
                    │  QUEUE   │  so the app never freezes waiting for OCR
                    └────┬─────┘
          ┌──────────────┼──────────────┐
    ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
    │ OCR       │  │ RULES     │  │ REPORTS   │
    │ worker    │  │ worker    │  │ worker    │
    │ reads     │  │ compares  │  │ makes PDF │
    │ the text  │  │ vs law    │  │ and Word  │
    └───────────┘  └───────────┘  └───────────┘
          │              │              │
    ┌─────▼──────────────▼──────────────▼─────┐
    │  DATABASE (Postgres)  ·  FILES (MinIO)  │
    └─────────────────────────────────────────┘
```

### 4.2 Why the work is split into "workers"

Reading text from a photo takes a second or two. If the app waited for it, every officer
would sit staring at a spinner. Instead:

1. The phone uploads and gets an immediate "got it".
2. The job goes on a queue.
3. Workers pick jobs up and do the slow parts.
4. The result appears on the officer's screen when ready.

If ten officers submit at once, you add more workers. Nothing else changes.

### 4.3 Where the law lives

The law is **not** on the server as PDFs either. It is compiled once, offline, into a small
file called the rulepack (about 14 KB) that the rules worker reads. See
[`06-RULEPACK.md`](06-RULEPACK.md).

### 4.4 How big a machine does it need

Smaller than people expect. Measured on an ordinary laptop CPU:

| Task | Time |
|---|---|
| Reading one photo | 1.6 seconds |
| A four-photo inspection, end to end | about 7 seconds |
| Budget we set ourselves | 15 seconds |

**A graphics card is optional, not required.** We previously claimed otherwise, and were
wrong — the timings we thought were from a GPU turned out to be CPU all along, because the
GPU was silently unavailable. The real fix for slowness was shrinking huge photos before
reading them, not buying hardware.

---

## 5. The tech stack

| Layer | What we use | Why |
|---|---|---|
| **Phone app** | PWA — a website that uses the camera | Works on any phone, no app store, no install |
| **Web console** | Next.js + TypeScript + Tailwind | The officer's review screen |
| **API** | FastAPI (Python) | One program, not twenty microservices |
| **Background jobs** | Redis + Dramatiq | So the app never freezes |
| **Reading photos** | PP-OCR via ONNX Runtime | Small, fast, runs anywhere. See §6 |
| **Image maths** | OpenCV | Straightening photos, measuring letters |
| **Word matching** | rapidfuzz | Matches `MR.P` to `MRP` despite typos. Not AI |
| **The rules** | Plain Python + a small rulepack file | Readable by a person. This is what makes it defensible |
| **Database** | PostgreSQL 16 | Scans, results, history, search |
| **File storage** | MinIO (or any S3-compatible) | Original photos, never modified |
| **Login and roles** | Keycloak | Standard OIDC, so department SSO plugs in later |
| **Reports** | WeasyPrint (PDF) + docxtpl (Word) | Both built from the same result |
| **Running it** | Docker Compose | One command. **No Kubernetes** |

**Not used, deliberately:** any AI chatbot or language model · Kubernetes · blockchain ·
Elasticsearch · cloud OCR services · a model that outputs "compliant / not compliant"
directly.

---

## 6. The OCR question — now that it is on the server, can we use a better model?

**Yes. And we should.** The size limit that mattered when we thought it shipped inside the
app does not apply on a server. But "bigger" is not automatically "better", so here is the
honest state of it.

### 6.1 What we found is actually wrong today

The model currently shipping is the **Chinese** recogniser. It has 6,625 characters and
**not one of them is Devanagari**. Hindi is not poorly supported — it is impossible. We
tested it: Hindi text came back as `00000.00000 2`.

### 6.2 The immediate fix costs nothing

| Model | Size | Reads Hindi? | Reads English? |
|---|---|---|---|
| Chinese *(what we ship now)* | 10.7 MB | **No** | Yes |
| English specialist | 9.0 MB | No | Yes, better |
| **Devanagari specialist** | **9.0 MB** | **Yes** | Yes |

Both specialists are **smaller** than the Chinese model. Running both is about 21 MB total
instead of 13.7 MB. On a server that is nothing.

Measured side by side on a Hindi label:

```
now:          '3  45.00'                'HT 500'
devanagari:   'अिधकतमखुदरामूलय...'      'शुदमाऋड००याम'
```

Not perfect — spacing and matras need work — but it is reading Hindi instead of not
reading it.

**Do this first. It is nearly free and unblocks half the country's labels.**

### 6.3 The bigger upgrade worth doing next

We are on **PP-OCR version 3**. Versions 4 and 5 exist and are more accurate. Version 5
has official models published, including larger "server" variants that we could not have
considered when we thought this ran on a phone.

Because it is server-side, these are now on the table:

| Option | Size | Trade-off |
|---|---|---|
| PP-OCRv3 specialists *(do now)* | ~21 MB | Nearly free, unblocks Hindi |
| **PP-OCRv5 mobile** | ~25 MB | Two generations newer, still light |
| **PP-OCRv5 server** | ~100 MB+ | Most accurate PP-OCR; needs more CPU or a GPU |

### 6.4 What we rejected, and why

| Option | Why not |
|---|---|
| **Surya** (a strong multilingual OCR) | It lists **`openai` as a dependency**. Our own CI rule forbids language-model packages in the shipped system, and would fail the build. It also needs PyTorch (~1 GB) and realistically a GPU |
| **TrOCR** | Transformer-based, slow, weak on Indic scripts |
| **EasyOCR** | PyTorch, heavier per language, slower than PP-OCR |
| **Google / Azure Vision** | Evidence would leave controlled infrastructure. Ruled out by the data-residency requirement, not by quality |

### 6.5 How we will actually decide

Not by picking a favourite. By measuring.

1. Build a labelled set of real Indian labels — English **and Hindi** — with the correct
   answers written down by hand.
2. Run each candidate over it.
3. Record two numbers per candidate: **how many declarations it reads correctly**, and
   **how many seconds per photo** on the hardware the department will actually have.
4. Pick the best accuracy that still fits the 15-second budget.

That evaluation harness is a small piece of work and should exist before anyone argues
about models again.

**Rule of thumb we are keeping:** the right model beats the big model. The current problem
was never that our model was too small — it was that it was the wrong language.

---

## 7. Summary in five lines

1. The phone takes photos and confirms it photographed everything. Nothing else.
2. The server reads, compares, stores, reports — because the problem statement asks for a
   repository, dashboards, search and roles, and none of those fit on one handset.
3. "Server" can be one machine in the department's own office.
4. It runs fine on an ordinary CPU. A graphics card is optional.
5. The OCR should be upgraded — starting with the Hindi model, which is nearly free and
   fixes something that is currently broken outright.
