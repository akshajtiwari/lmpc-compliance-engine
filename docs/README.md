# Documentation

Legal Metrology (Packaged Commodities) Rules, 2011 — automated compliance checking.

## Read in this order

| # | Document | Audience | Time |
|---|---|---|---|
| 0 | [`00-TEAM-BRIEF.md`](00-TEAM-BRIEF.md) | Everyone, before writing any code. Plain English. | 8 min |
| 1 | [`01-ARCHITECTURE.md`](01-ARCHITECTURE.md) | Anyone making design decisions. | 20 min |
| 2 | [`02-BUILD-SPEC.md`](02-BUILD-SPEC.md) | **The implementation document.** Every threshold, schema and refusal path. | reference |
| 3 | [`03-ENGINEERING-PLAN.md`](03-ENGINEERING-PLAN.md) | What gets built, by whom, in what order. | 15 min |
| 4 | [`04-FLOW.md`](04-FLOW.md) | One scan end to end: what the user sees, what runs. | 5 min |

## Evidence

Every number in the spec and plan traces to one of these. They were produced by running
the system, not by estimating.

| Report | Establishes |
|---|---|
| [`evidence/LAW-COMPILER-TEST.md`](evidence/LAW-COMPILER-TEST.md) | The law compiles automatically from live government sources |
| [`evidence/END-TO-END-STRESS-TEST.md`](evidence/END-TO-END-STRESS-TEST.md) | Verdict behaviour under OCR noise — 7 defects found |
| [`evidence/VALIDATION-CAMPAIGN.md`](evidence/VALIDATION-CAMPAIGN.md) | Ingestion, compilation and comparison under attack — 5 architectural defects |
| [`evidence/REAL-WORLD-TEST.md`](evidence/REAL-WORLD-TEST.md) | 60 real Indian food products, real OCR — 5 defects |
| [`evidence/WIDE-REAL-WORLD-TEST.md`](evidence/WIDE-REAL-WORLD-TEST.md) | 80 more products across cosmetics, household, pet food — 3 defects, resolution budget |

## Source material

`source-extracts/` holds primary text pulled from official sources on 2026-09-04.

| File | What it is |
|---|---|
| `LMPC-2011-consolidated-to-2021-10-31.txt` | English-only consolidated rules. Baseline, **not authoritative for current law** |
| `GSR-2017-amendment-gazette.txt` | The instrument that replaced Rule 7 Table-I and omitted Table-II |
| `GSR-577E-2022-QR-code-amendment.txt` | A clean example of the amendment grammar |
| `base-2011-p47-OLD-table-I.png` | Page 47 of the base scan showing the **repealed** table — the demo exhibit |

## Archive

`archive/` holds superseded documents, kept for traceability. **They are not build
inputs.** The technical spec there contains rule values that were wrong against the
notified law; see `02-BUILD-SPEC.md` Part M.
