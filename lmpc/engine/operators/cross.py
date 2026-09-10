"""Operators 8–12 — cross_field, script_allowed, mrp_uniqueness, date_plausible,
small_package_mark."""
from __future__ import annotations
import datetime as dt
import re
from .. import normalize
from ..model import Verdict, Result, Scan, Field
from ._common import r, lexicon_match


# ---------------------------------------------------------------- 8. cross_field ---
def cross_field(spec, scan: Scan, fields) -> Result:
    mrp, qty, usp = fields.get("mrp"), fields.get("net_quantity"), fields.get("unit_sale_price")
    if not (mrp and qty and usp):
        return r(spec, Verdict.NOT_APPLICABLE, "needs MRP, quantity and unit price together")
    m = normalize.money(usp.text)
    if not m or not qty.normalized.get("value"):
        return r(spec, Verdict.INDETERMINATE, "could not read the unit price")
    per = 1000 if qty.normalized["value"] >= 1000 else 1
    expected = mrp.normalized["amount"] / (qty.normalized["value"] / per)
    dev = abs(expected - m["amount"]) / expected * 100 if expected else 100.0
    if dev <= spec["params"]["tolerance_pct"]:
        return r(spec, Verdict.PASS, f"unit price consistent ({dev:.1f}% deviation)",
                 expected=round(expected, 2), declared=m["amount"])
    return r(spec, Verdict[spec["params"]["on_mismatch"]],
             f"unit price deviates {dev:.1f}% from MRP / quantity",
             expected=round(expected, 2), declared=m["amount"])


# ------------------------------------------------------------- 9. script_allowed ---
_SCRIPTS = {"DEVANAGARI": re.compile(r"[ऀ-ॿ]"),
            "LATIN": re.compile(r"[A-Za-z]"),
            "BENGALI": re.compile(r"[ঀ-৿]"),
            "TAMIL": re.compile(r"[஀-௿]"),
            "TELUGU": re.compile(r"[ఀ-౿]"),
            "ARABIC": re.compile(r"[؀-ۿ]"),
            "CJK": re.compile(r"[一-鿿぀-ヿ]")}


def script_allowed(spec, scan: Scan, fields) -> Result:
    """Rule 9(4). Declarations must appear in Hindi (Devanagari) or English.

    The proviso permits any other language IN ADDITION, so finding a third script is not
    itself a violation - only the ABSENCE of both permitted scripts is.
    """
    p = spec["params"]
    seen = set()
    for f in fields.values():
        if not f:
            continue
        for name, pat in _SCRIPTS.items():
            if pat.search(f.text):
                seen.add(name)
    if not seen:
        return r(spec, Verdict.INDETERMINATE, "no declaration text was established")
    permitted = seen & set(p["allowed_scripts"])
    extra = sorted(seen - set(p["allowed_scripts"]))
    if permitted:
        note = f" (also present: {', '.join(extra)}, permitted in addition)" if extra else ""
        return r(spec, Verdict.PASS,
                 f"declarations appear in {', '.join(sorted(permitted))}{note}",
                 scripts=sorted(seen))
    return r(spec, Verdict.FAIL,
             f"declarations appear only in {', '.join(extra)}; Hindi in Devanagari or "
             f"English is required", scripts=sorted(seen))


# ------------------------------------------------------------ 10. mrp_uniqueness ---
def mrp_uniqueness(spec, scan: Scan, fields) -> Result:
    """Rule 6(3). A sticker may not alter a declaration, except a revised LOWER MRP that
    does not cover the original. Two prices on one pack always needs a human."""
    prices = []
    for t in scan.tokens:
        if lexicon_match(t.text) and (m := normalize.money(t.text, require_currency=False)):
            prices.append(m["amount"])
    prices = sorted(set(prices))
    if len(prices) < 2:
        return r(spec, Verdict.NOT_APPLICABLE, "a single retail price was declared",
                 prices=prices)
    return r(spec, Verdict[spec["params"]["on_two_values"]],
             f"{len(prices)} different retail prices found on the package ({prices}); "
             f"lawful only as a revised lower price that does not cover the original",
             prices=prices)


# ------------------------------------------------------------- 11. date_plausible ---
def date_plausible(spec, scan: Scan, fields) -> Result:
    """A packing date after the inspection, or before these rules commenced, is a misprint
    or a misreading. Neither is a conclusion a machine should reach on its own."""
    f = fields.get(spec["field"])
    if not f or "year" not in (f.normalized or {}):
        return r(spec, Verdict.NOT_APPLICABLE, "no date established")
    y, m = f.normalized["year"], f.normalized["month"]
    when = dt.date(y, m, 1)
    # not_after is either a literal ISO date or 'inspection_date' (the default).
    na = spec["params"].get("not_after")
    insp = (dt.date.fromisoformat(na) if na and na != "inspection_date"
            else dt.date.fromisoformat(scan.captured_at))
    floor = dt.date.fromisoformat(spec["params"]["not_before"])
    if when > insp:
        return r(spec, Verdict[spec["params"]["on_violation"]],
                 f"declared packing date {m:02d}/{y} is after the inspection "
                 f"({scan.captured_at})", declared=f"{m:02d}/{y}")
    if when < floor:
        return r(spec, Verdict[spec["params"]["on_violation"]],
                 f"declared packing date {m:02d}/{y} precedes the commencement of these "
                 f"rules", declared=f"{m:02d}/{y}")
    return r(spec, Verdict.PASS, f"packing date {m:02d}/{y} is plausible",
             declared=f"{m:02d}/{y}")


# -------------------------------------------------------- 12. small_package_mark ---
def small_package_mark(spec, scan: Scan, fields) -> Result:
    """Rule 10(1) proviso, as raised from 5 to 10 cubic cm in 2017: on a very small
    package an identifying mark suffices instead of the full name and address."""
    cap = scan.capacity_cm3
    if cap is None:
        return r(spec, Verdict.NOT_APPLICABLE, "package capacity not supplied")
    if cap > spec["params"]["capacity_cm3_at_or_below"]:
        return r(spec, Verdict.NOT_APPLICABLE,
                 f"capacity {cap} cm3 exceeds the "
                 f"{spec['params']['capacity_cm3_at_or_below']} cm3 relaxation")
    ident = fields.get("manufacturer_block") or fields.get("brand_name")
    return r(spec, Verdict.PASS if ident else Verdict.INDETERMINATE,
             "an identifying mark suffices at this capacity" if ident else
             "no identifying mark was established on a package eligible for the relaxation",
             capacity_cm3=cap)