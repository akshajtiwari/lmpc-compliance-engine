"""Render a scan result the way an officer must see it: every verdict with the number
measured, the number required, the clause, and where in the gazette it comes from."""
from __future__ import annotations
from .model import Verdict

SYMBOL = {Verdict.PASS: "PASS", Verdict.FAIL: "FAIL",
          Verdict.INDETERMINATE: "UNDETERMINED", Verdict.NOT_APPLICABLE: "N/A",
          Verdict.REVIEW_REQUIRED: "REVIEW", Verdict.SYSTEM_ERROR: "ERROR"}


def render(res: dict) -> str:
    rp = res["rulepack"]
    out = [f"COMPLIANCE REPORT — {res['overall']}",
           f"rulepack {rp['version']} · sha {rp['sha256']} · current to {rp['current_to']}"]
    if res["gates_fired"]:
        out.append(f"applicability gates fired: {', '.join(res['gates_fired'])}")
    out.append("")
    for r in res["results"]:
        if r.verdict is Verdict.NOT_APPLICABLE and not res["gates_fired"]:
            continue
        c = r.citation or {}
        cite = f"{c.get('gsr','')} p.{c.get('page','?')}" if c else "—"
        out.append(f"[{SYMBOL[r.verdict]:^12}] {r.clause:<22} {r.check}")
        out.append(f"               {r.reason}")
        if r.evidence:
            ev = ", ".join(f"{k}={v}" for k, v in r.evidence.items()
                           if v is not None and not k.startswith("_"))
            if ev:
                out.append(f"               evidence: {ev[:150]}")
        out.append(f"               authority: {cite}")
        out.append("")
    for d in res["disclosures"]:
        out.append(f"DISCLOSURE: {d}")
    return "\n".join(out)
