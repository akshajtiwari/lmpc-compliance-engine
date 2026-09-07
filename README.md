# LMPC Compliance Engine

Checks packaged-commodity labels against the Legal Metrology (Packaged Commodities)
Rules, 2011 — including every amendment up to **G.S.R. 418(E), 29 May 2026**.

No language model anywhere. The problem statement asks for *rule-based* checking; that is
literally what runs.

```
gazette PDFs ──> law compiler ──> rulepack (versioned, hashed)
                                       │
label photo ──> OCR ──> match ──> pick ──> normalise ──> measure ──> RULE ENGINE ──> verdicts
```

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m lmpc.lawc.build            # fetch gazettes, compile, write rulepack
python -m stress.run                 # end-to-end stress test
pytest -q                            # unit + integration tests
```

Design documents live in `docs/`. Start with `docs/00-TEAM-BRIEF.md`.
