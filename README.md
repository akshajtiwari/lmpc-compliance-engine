# LMPC Compliance Engine

Automated compliance checking of packaged-commodity labels against the **Legal Metrology
(Packaged Commodities) Rules, 2011** — including every amendment up to
**G.S.R. 418(E), 29 May 2026**.

No language model. The problem statement asks for *rule-based* checking; that is literally
what runs. Vision AI produces evidence, deterministic Python draws every conclusion.

```
gazette PDFs ──► law compiler ──► rulepack (versioned, hashed, dated)
                                        │
label photos ──► OCR ──► layout ──► scoring ──► normalise ──► RULE ENGINE ──► verdicts
```

## Validated, not asserted

| | |
|---|---|
| Real products tested | **140** — food, cosmetics, household, pet food |
| Real photographs | **403** |
| Real gazette instruments compiled | **48** across 3 rule families |
| Rule evaluations run | **2,700** |
| **False accusations** | **0** |
| Violations silently passed | **0** |
| Defects found and fixed by testing | **20** |

The system answers confidently to roughly 10 % character error, then stops answering
rather than guessing.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt          # + onnxruntime-gpu if you have CUDA

python -m lmpc.lawc.build                # fetch gazettes, compile, write the rulepack
pytest -q                                # unit, contract and adversarial tests
python -m stress.run                     # 22 scenarios, noise and sensitivity sweeps
python -m stress.campaign                # 24 validation checks
python -m stress.realworld food          # real photographs, real OCR
```

## Run the local API (no S3 required)

The development stack uses PostgreSQL in Docker and stores immutable images and reports
under `.lmpc-data/objects` on this machine. It does not install or contact S3.

```bash
cp .env.example .env
make setup                               # once, if .venv is not already installed
make dev                                 # migrates, seeds a local officer, serves :8000
```

Open `http://127.0.0.1:8000/` for the installable guided capture app and
`http://127.0.0.1:8000/docs` for the API explorer. The capture app keeps drafts and an
outbox in IndexedDB, so an interrupted or offline upload can be retried with the same
client UUID. The local API also exposes jurisdiction-scoped scan search, append-only
declaration corrections, evaluation-batch history and reasoned verdict overrides. A
correction is reused by later deterministic evaluation batches; the OCR original is never
deleted. `/metrics` exposes local Prometheus counters, including the zero-tolerance
FAIL-without-coverage guard; API responses carry correlation IDs and rate-limit headers.
Run the PostgreSQL round-trip with `make test-db`; run all deterministic suites with
`make test`; stop PostgreSQL with `make db-down` (the named volume keeps its data).

The example environment enables the local-password path with
`reviewer@local.invalid` and the password shown in `.env.example`. Change that password
before sharing the machine or exposing the port; it is a development bootstrap account,
not a production credential. Access tokens stay in browser memory; the rotating refresh
token is held in an HttpOnly, SameSite cookie.

The dormant S3-compatible adapter is optional. Install `requirements-s3.txt` only when a
bucket is available and `LMPC_S3_BUCKET` is intentionally configured.

`python -m lmpc.lawc.build` refuses to produce a rulepack it cannot prove is current,
correct and intact. That is the intended behaviour, not a failure.

## What is here

| Path | |
|---|---|
| `lmpc/lawc/` | The law compiler: gazette PDFs → a hashed rulepack |
| `lmpc/engine/` | OCR, layout, extraction, the twelve operators, the rule engine |
| `lmpc/labels/` | Synthetic labels with exact ground truth; real-photo harvesting |
| `stress/` | Scenario, campaign, real-world and resolution suites |
| `tests/` | Unit, integration and adversarial fail-tests |
| `docs/` | **Start with [`docs/README.md`](docs/README.md)** — new joiners: `00-TEAM-BRIEF` then `05-SYSTEM-MAP` |

## Design in one paragraph

The law is compiled once, offline, into a small versioned rulepack; no scan ever reads a
PDF. Instrument identity is (G.S.R. number, **year**) because numbers restart annually and
collide. A scan is judged by the law in force on the day it was captured, so repealed
tables are retained rather than deleted. There are six verdicts, not two: "we could not
find the MRP" and "the MRP is missing" are different findings, and the second requires the
capture app to have confirmed every surface was photographed. Where a measurement cannot
support the claim being made, the system abstains and says why.

## Licence and status

Prototype built for the Smart India Hackathon problem statement on Legal Metrology
compliance. Rule values are compiled from primary gazette text with a recorded reviewer,
but **production use requires sign-off by a qualified Legal Metrology officer** — see
`docs/02-BUILD-SPEC.md` Part N.
