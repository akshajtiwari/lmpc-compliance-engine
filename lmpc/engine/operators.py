"""
The six generic operators. Written once, as ordinary code a person can read.

Everything specific to a rule — the numbers, the regexes, the tables — arrives as
parameters from the rulepack. That separation is why a new amendment needs no code
change: the parameters reload, these functions do not move.
"""
from __future__ import annotations
import re
from .model import Verdict, Result, Scan, Field
from . import normalize


def _r(spec, verdict, reason, **ev) -> Result:
    return Result(check=spec["check"], clause=spec["clause"], verdict=verdict,
                  reason=reason, citation=spec.get("citation", {}), evidence=ev)


# ------------------------------------------------------------------ 1. presence ---
def presence(spec, scan: Scan, fields: dict[str, Field | None]) -> Result:
    f = fields.get(spec["field"])
    if f:
        return _r(spec, Verdict.PASS, f"found on {f.panel} panel",
                  text=f.text, score=f.score, margin=f.margin, panel=f.panel)
    # Absence of evidence is not evidence of absence. If a surface was never
    # photographed, we cannot say the declaration is missing.
    if scan.panels_captured != {"FRONT", "BACK", "SIDE"} - (
            {"SIDE"} - scan.panels_captured):
        pass
    if not {"FRONT", "BACK"} <= scan.panels_captured:
        missing = sorted({"FRONT", "BACK"} - scan.panels_captured)
        return _r(spec, Verdict.INDETERMINATE,
                  f"not found, but {', '.join(missing)} panel(s) were never photographed",
                  panels_captured=sorted(scan.panels_captured))
    return _r(spec, Verdict.FAIL, "declaration not found on any photographed panel",
              panels_captured=sorted(scan.panels_captured))


# -------------------------------------------------------------- 2. format_regex ---
def format_regex(spec, scan: Scan, fields) -> Result:
    f = fields.get(spec["field"])
    if not f:
        return _r(spec, Verdict.NOT_APPLICABLE, "field not established; presence check governs")
    if re.search(spec["params"]["regex"], f.text):
        return _r(spec, Verdict.PASS, "matches the prescribed form", text=f.text)
    return _r(spec, Verdict.FAIL, "does not match the prescribed form",
              text=f.text, expected=spec["params"].get("illustrations"))


# ---------------------------------------------------------- 3. numeric_predicate ---
def numeric_predicate(spec, scan: Scan, fields) -> Result:
    f = fields.get(spec["field"])
    if not f or "amount" not in f.normalized:
        return _r(spec, Verdict.NOT_APPLICABLE, "no numeric value established")
    amt = f.normalized["amount"]
    pred = spec["params"]["predicate"]
    ok = getattr(normalize, pred)(amt)
    return _r(spec, Verdict.PASS if ok else Verdict.FAIL,
              f"{amt} {'satisfies' if ok else 'violates'} {pred}", amount=amt)


# ------------------------------------------------------------- 4. tiered_format ---
def tiered_format(spec, scan: Scan, fields) -> Result:
    usp, qty = fields.get("unit_sale_price"), fields.get("net_quantity")
    if not usp:
        return _r(spec, Verdict.NOT_APPLICABLE, "no unit sale price declared")
    if not qty or "unit" not in qty.normalized:
        return _r(spec, Verdict.INDETERMINATE, "net quantity not established; cannot pick the tier")
    v, u = qty.normalized["value"], qty.normalized["unit"]
    want = ("Rs. _ per kg" if u == "g" and v >= 1000 else
            "Rs. _ per g" if u == "g" else
            "Rs. _ per litre" if u == "ml" and v >= 1000 else
            "Rs. _ per ml" if u == "ml" else "Rs. _ per number")
    unit_word = want.rsplit(" ", 1)[-1]
    ok = re.search(rf"per\s+{unit_word}\b", usp.text, re.I)
    return _r(spec, Verdict.PASS if ok else Verdict.FAIL,
              f"quantity {v}{u} requires the form '{want}'", declared=usp.text, required=want)


# ----------------------------------------------------------------- 5. ratio_min ---
def ratio_min(spec, scan: Scan, fields) -> Result:
    """Rule 7(3). A pure pixel ratio — no scale reference needed."""
    p = spec["params"]
    excl = set(p.get("exclude_glyphs", []))
    worst = None
    for f in fields.values():
        if not f:
            continue
        for t in f.tokens:
            letters = [c for c in t.text if c.isalnum() and c not in excl]
            if not letters or not t.h:
                continue
            ratio = (t.w / len(t.text)) / t.h        # mean advance width over line height
            if worst is None or ratio < worst[0]:
                worst = (ratio, t.text)
    if worst is None:
        return _r(spec, Verdict.INDETERMINATE, "no measurable glyphs")
    ratio, text = worst
    ok = ratio >= p["min"]
    return _r(spec, Verdict.PASS if ok else Verdict.FAIL,
              f"narrowest mean width/height ratio {ratio:.3f} vs minimum {p['min']}",
              ratio=round(ratio, 3), minimum=p["min"], text=text)


# --------------------------------------------------------------- 6. clear_space ---
def clear_space(spec, scan: Scan, fields) -> Result:
    """Rule 8. Also a pure pixel ratio: distance to the nearest other printed matter,
    measured in multiples of the quantity numeral's own height."""
    p = spec["params"]
    f = fields.get(p["field"])
    if not f:
        return _r(spec, Verdict.NOT_APPLICABLE, "quantity declaration not established")
    q = f.tokens[0]
    need_v, need_h = p["above_below_multiple"] * q.h, p["left_right_multiple"] * q.h
    got_v = got_h = float("inf")
    for t in scan.tokens:
        if t is q or t.panel != q.panel:
            continue
        if t.x < q.x + q.w and t.x + t.w > q.x:                     # vertically aligned
            got_v = min(got_v, q.y - (t.y + t.h) if t.y < q.y else t.y - (q.y + q.h))
        if t.y < q.y + q.h and t.y + t.h > q.y:                     # horizontally aligned
            got_h = min(got_h, q.x - (t.x + t.w) if t.x < q.x else t.x - (q.x + q.w))
    ok = got_v >= need_v and got_h >= need_h
    return _r(spec, Verdict.PASS if ok else Verdict.FAIL,
              f"clear space above/below {got_v:.0f}px (need {need_v:.0f}), "
              f"left/right {got_h:.0f}px (need {need_h:.0f})",
              above_below_px=None if got_v == float("inf") else round(got_v),
              left_right_px=None if got_h == float("inf") else round(got_h),
              numeral_height_px=q.h)


# -------------------------------------------------------------- 7. table_lookup ---
def table_lookup(spec, scan: Scan, fields) -> Result:
    """Rule 7(2) Table-I. The only check that needs a real-world scale reference."""
    p = spec["params"]
    area = scan.pdp_area_cm2()
    if area is None:
        return _r(spec, Verdict.INDETERMINATE,
                  "package dimensions not supplied; principal display panel area unknown")
    if scan.px_per_mm is None:
        return _r(spec, Verdict.INDETERMINATE,
                  "no scale reference in frame; millimetre height cannot be measured")

    band, lo = None, 0.0
    for row in p["rows"]:
        hi = row["upper_cm2"]
        if hi is None or area <= hi:
            band = row
            break
        lo = hi
    edges = [e for e in (lo, band["upper_cm2"]) if e]
    guard = spec.get("boundary_review", {}).get("guard_band_cm2", 0.0)
    if spec.get("verdict_ceiling") == "INDETERMINATE_NEAR_BOUNDARY" and \
       any(abs(area - e) <= guard for e in edges):
        return _r(spec, Verdict.INDETERMINATE,
                  f"panel area {area:.1f} cm2 sits within {guard} cm2 of a Table-I "
                  f"boundary whose '<' vs '≤' reading is unresolved",
                  pdp_area_cm2=round(area, 1), boundary=edges)

    required = band["molded_mm"] if scan.is_molded else band["min_mm"]
    measured = max((t.cap_height_px or t.h) for f in fields.values() if f for t in f.tokens
                   if f.kind in ("mrp", "net_quantity")) / scan.px_per_mm
    unc = 1.0 / scan.px_per_mm                      # one pixel, expressed in mm
    ev = dict(pdp_area_cm2=round(area, 1), measured_mm=round(measured, 2),
              uncertainty_mm=round(unc, 2), required_mm=required,
              band=band["band_as_printed"], molded=scan.is_molded,
              source=p.get("source_instrument"))
    if abs(measured - required) <= unc:
        return _r(spec, Verdict.INDETERMINATE,
                  f"measured {measured:.2f} +/- {unc:.2f} mm straddles the {required} mm "
                  f"threshold", **ev)
    ok = measured >= required
    return _r(spec, Verdict.PASS if ok else Verdict.FAIL,
              f"measured {measured:.2f} mm against a required {required} mm for a "
              f"{area:.0f} cm2 panel", **ev)


# ---------------------------------------------------------------- 8. cross_field ---
def cross_field(spec, scan: Scan, fields) -> Result:
    mrp, qty, usp = fields.get("mrp"), fields.get("net_quantity"), fields.get("unit_sale_price")
    if not (mrp and qty and usp):
        return _r(spec, Verdict.NOT_APPLICABLE, "needs MRP, quantity and unit price together")
    m = normalize.money(usp.text)
    if not m or not qty.normalized.get("value"):
        return _r(spec, Verdict.INDETERMINATE, "could not read the unit price")
    per = 1000 if qty.normalized["value"] >= 1000 else 1
    expected = mrp.normalized["amount"] / (qty.normalized["value"] / per)
    dev = abs(expected - m["amount"]) / expected * 100 if expected else 100.0
    if dev <= spec["params"]["tolerance_pct"]:
        return _r(spec, Verdict.PASS, f"unit price consistent ({dev:.1f}% deviation)",
                  expected=round(expected, 2), declared=m["amount"])
    return _r(spec, Verdict[spec["params"]["on_mismatch"]],
              f"unit price deviates {dev:.1f}% from MRP / quantity",
              expected=round(expected, 2), declared=m["amount"])


OPERATORS = {
    "presence": presence, "format_regex": format_regex,
    "numeric_predicate": numeric_predicate, "tiered_format": tiered_format,
    "ratio_min": ratio_min, "clear_space": clear_space,
    "table_lookup": table_lookup, "cross_field": cross_field,
}
