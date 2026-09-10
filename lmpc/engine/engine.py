"""
The rule engine. Applicability first, then checks, then an overall status.

Order matters more than anything else here: a package the law does not govern must never
reach a declaration check. Running presence checks on an exempt package is how an
automated system accuses someone of breaking a rule that never applied to them.
"""
from __future__ import annotations
import datetime as _dt

from .model import Verdict, Result, Scan
from .operators import OPERATORS
from .extract import extract

FIELD_KINDS = ["mrp", "net_quantity", "mfg_date", "consumer_care",
               "manufacturer_block", "country_of_origin", "generic_name",
               "unit_sale_price"]


def in_force(spec: dict, on: str) -> bool:
    """Was this requirement law on the day of the inspection?"""
    d = _dt.date.fromisoformat(on)
    fr = spec.get("effective_from")
    to = spec.get("effective_to")
    if fr and d < _dt.date.fromisoformat(str(fr)):
        return False
    if to and d > _dt.date.fromisoformat(str(to)):
        return False
    return True


def _cond(c: dict, scan: Scan) -> bool:
    v = getattr(scan, c["field"], None)
    if "unless_field" in c and getattr(scan, c["unless_field"], None) in c["unless_in"]:
        return False
    if "in" in c and v not in c["in"]:
        return False
    if "eq" in c and v != c["eq"]:
        return False
    if "gt" in c and not (v is not None and v > c["gt"]):
        return False
    if "lte" in c and not (v is not None and v <= c["lte"]):
        return False
    if "and_field" in c:
        av = getattr(scan, c["and_field"], None)
        if not (av is not None and av > c["gt"]):
            return False
    return any(k in c for k in ("in", "eq", "gt", "lte"))


def run_gates(pack: dict, scan: Scan) -> list[dict]:
    fired = []
    for g in pack["gates"]:
        p = g["params"]
        hit = (any(_cond(c, scan) for c in p["any_of"]) if "any_of" in p
               else _cond(p["when"], scan))
        if hit:
            fired.append(g)
    return fired


def _typography_skips(pack: dict, fired: list[dict]) -> set[str]:
    """Rule 7(5): a gate with SKIP_TYPOGRAPHY_EXCEPT removes the typography checks —
    those bound to Rule 7 or Rule 8 nodes — except the check IDs the gate names."""
    skip = set()
    for g in fired:
        if g["effect"] != "SKIP_TYPOGRAPHY_EXCEPT":
            continue
        keep = set(g.get("exceptions") or [])
        skip |= {c["check"] for c in pack["checks"]
                 if c["node"].startswith(("lmpc/r7", "lmpc/r8"))
                 and c["check"] not in keep}
    return skip


def _relaxed_checks(pack: dict, scan: Scan) -> set[str]:
    """Rule 10(1) proviso: on a package at or below the binding's capacity an identifying
    mark suffices, so the checks a small_package_mark binding names are not required."""
    out = set()
    for c in pack["checks"]:
        p = c.get("params") or {}
        if c["operator"] != "small_package_mark" or "relaxes" not in p:
            continue
        cap = scan.capacity_cm3
        if cap is not None and cap <= p["capacity_cm3_at_or_below"]:
            out.add(p["relaxes"])
    return out


def _not_required(cond: dict, scan: Scan) -> bool:
    if "scan_mode" in cond:
        return scan.mode == cond["scan_mode"]
    return _cond(cond, scan)


def run(pack: dict, scan: Scan, fields=None) -> dict:
    fired = run_gates(pack, scan)
    stop = next((g for g in fired if g["effect"] in
                 ("ALL_RULES_NOT_APPLICABLE", "CHAPTER_II_NOT_APPLICABLE")), None)
    excluded = set(pack["modes"].get(scan.mode, {}).get("excludes") or [])
    skip_typo = _typography_skips(pack, fired)
    relaxed = _relaxed_checks(pack, scan)

    if stop:
        results = [Result(check=c["check"], clause=c["clause"],
                          verdict=Verdict.NOT_APPLICABLE,
                          reason=f"{stop['id']} ({stop['clause']}) — {stop['effect']}",
                          citation=stop["citation"]) for c in pack["checks"]]
        return _summarise(pack, scan, results, fired, {})

    if fields is None:
        fields = extract(scan, FIELD_KINDS)
    results = []
    for c in pack["checks"]:
        if not in_force(c, scan.captured_at):
            results.append(Result(c["check"], c["clause"], Verdict.NOT_APPLICABLE,
                                  f"not in force on {scan.captured_at} "
                                  f"(effective from {c.get('effective_from')})",
                                  c.get("citation", {})))
            continue
        if c["check"] in excluded:
            results.append(Result(c["check"], c["clause"], Verdict.NOT_APPLICABLE,
                                  f"not required in {scan.mode} (Rule 6(10))",
                                  pack["modes"][scan.mode].get("citation", {})))
            continue
        if c["check"] in relaxed:
            results.append(Result(c["check"], c["clause"], Verdict.NOT_APPLICABLE,
                                  "relaxed by the small-package proviso (Rule 10(1))",
                                  c.get("citation", {})))
            continue
        if "not_required_when" in c and _not_required(c["not_required_when"], scan):
            results.append(Result(c["check"], c["clause"], Verdict.NOT_APPLICABLE,
                                  "binding exempts this scan from this requirement",
                                  c.get("citation", {})))
            continue
        if c["check"] in skip_typo:
            results.append(Result(c["check"], c["clause"], Verdict.NOT_APPLICABLE,
                                  "Rule 7(5): the same information is required by another law",
                                  c.get("citation", {})))
            continue
        if "only_when" in c and not all(
                getattr(scan, k, None) == v for k, v in c["only_when"].items()):
            results.append(Result(c["check"], c["clause"], Verdict.NOT_APPLICABLE,
                                  "condition for this declaration not met", c.get("citation", {})))
            continue
        op = OPERATORS.get(c["operator"])
        if op is None:
            results.append(Result(c["check"], c["clause"], Verdict.SYSTEM_ERROR,
                                  f"no operator '{c['operator']}'", c.get("citation", {})))
            continue
        try:
            results.append(_ceiling(c, op(c, scan, fields)))
        except Exception as e:                      # never let a bug read as a violation
            results.append(Result(c["check"], c["clause"], Verdict.SYSTEM_ERROR,
                                  f"{type(e).__name__}: {e}", c.get("citation", {})))
    return _summarise(pack, scan, results, fired, fields)


def _ceiling(spec, r: Result) -> Result:
    """A check may declare a verdict it is not entitled to reach.

    Used where the law is unresolved (Table-I boundaries) or where extraction is not
    reliable enough to accuse anyone (the generic name). The measurement and the
    reasoning still appear — only the accusation is withheld."""
    cap = spec.get("verdict_ceiling")
    # INDETERMINATE_NEAR_BOUNDARY is enforced inside table_lookup, which knows where the
    # boundaries are. Only an absolute ceiling withholds every FAIL.
    if cap == "INDETERMINATE" and r.verdict is Verdict.FAIL:
        return Result(r.check, r.clause, Verdict.INDETERMINATE,
                      f"{r.reason} — withheld from FAIL: "
                      f"{' '.join(spec.get('ceiling_reason', cap).split())}",
                      r.citation, r.evidence)
    return r


def _summarise(pack, scan, results, fired, fields) -> dict:
    counts = {v.value: sum(1 for r in results if r.verdict is v) for v in Verdict}
    overall = ("SYSTEM_ERROR" if counts["SYSTEM_ERROR"] else
               "NON_COMPLIANT" if counts["FAIL"] else
               "REVIEW_REQUIRED" if counts["REVIEW_REQUIRED"] else
               "INCOMPLETE_EVIDENCE" if counts["INDETERMINATE"] else
               "OUT_OF_SCOPE" if counts["NOT_APPLICABLE"] == len(results) else
               "COMPLIANT")
    return {
        "overall": overall,
        "counts": counts,
        "gates_fired": [g["id"] for g in fired],
        "results": results,
        "fields": {k: (v.text if v else None) for k, v in fields.items()},
        "rulepack": {"version": pack["version"], "sha256": pack["sha256"],
                     "current_to": pack["currency"]["newest_instrument"]},
        "disclosures": [d["text"] for d in pack["currency"]["acknowledged_gaps"]],
    }
