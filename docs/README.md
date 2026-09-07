# SIH — Legal Metrology Packaged Commodities Compliance System

Planning documents for the SIH problem statement on automated compliance checking of
packaged commodity labels under the Legal Metrology (Packaged Commodities) Rules, 2011.

## Read in this order

| # | Document | Audience | Length |
|---|---|---|---|
| 0 | [`00-TEAM-BRIEF.md`](00-TEAM-BRIEF.md) | The whole team. Read before writing any code. | ~5 min |
| 1 | [`01-ARCHITECTURE.md`](01-ARCHITECTURE.md) | Anyone making design decisions. | ~20 min |
| 2 | [`03-BUILD-GUIDE.md`](03-BUILD-GUIDE.md) | **Start here to actually write code.** Tools, real code, week-by-week. | ~25 min |
| 3 | [`02-ENGINEERING-SPEC.md`](02-ENGINEERING-SPEC.md) | Deep reference. Full schemas, production-grade detail. | reference |

> **Note on 02 vs 03.** `02-ENGINEERING-SPEC.md` describes the system as it would be built
> for real (signed rulepacks, WORM storage, legal reviewers). `03-BUILD-GUIDE.md` is the
> hackathon-sized version of the same design — a YAML file in git instead of a signed
> rulepack, a folder instead of object storage. Build 03. Read 02 to answer judges.

## Source extracts

`source-extracts/` holds material pulled from the official sources on 2026-09-04:

| File | What it is |
|---|---|
| `LMPC-2011-consolidated-to-2021-10-31.txt` | English-only consolidated rules text (97k chars), from the Maharashtra LM portal. **Baseline for the rulepack** — not authoritative for current law. |
| `GSR-2017-amendment-gazette.txt` | Primary gazette text of the 2017 amendment — the instrument that replaced Rule 7 Table-I and omitted Table-II. |
| `GSR-577E-2022-QR-code-amendment.txt` | The QR-code amendment; a clean example of the amendment grammar. |
| `base-2011-p47-OLD-table-I.png` | Page 47 of the base 2011 scan, showing the **repealed** net-quantity-based Table-I. Keep this — it is the demo exhibit. |

## The three things that most change the plan

1. **The base 2011 PDF is out of date on the hardest requirement.** The 2017 amendment
   replaced the letter-height table: it is keyed to **principal display panel area in
   cm²**, not net quantity. Building from the base PDF implements repealed law.

2. **A clean, English-only, fully text-extractable consolidated version already exists.**
   You do not need to OCR the 83-page bilingual scan to get started.

3. **Two font/placement checks need no physical calibration at all** — letter width ≥ ⅓
   height (Rule 7(3)) and the clear-space ratios around the quantity declaration
   (Rule 8). Pure pixel ratios. Build them before the AprilTag pipeline.

## Council analysis

The full external review that informed these documents is archived at
`../.claude/council-cache/council-agents-1788466125.md` (codex / gpt-5.6-sol,
55k chars, agent-enhanced).
