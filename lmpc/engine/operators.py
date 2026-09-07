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


# Characters a recogniser routinely swaps. Correcting them can only ever DOWNGRADE a
# FAIL to INDETERMINATE - it never manufactures a PASS - so over-correcting is safe.
# G->6 and Z->2 were tried and removed: the stress run showed them corrupting "MFG02"
# into "MF 602", turning a compliant date into a violation. A repair that can damage a
# neighbouring word is worse than no repair.
_OCR_FIX = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "B": "8"})


_NUMERIC_RUN = re.compile(r"[0-9OolISB.,]{2,}")


def fix_numerals(text: str) -> str:
    """Undo digit/letter confusions inside numeric runs only.

    Translating the whole string would break the words the rule depends on: 'Rs.' becomes
    'R5.' and 'incl.' becomes 'inc1.', so a compliant label would still read as a
    violation. Only runs that already contain a real digit are corrected."""
    def sub(m):
        run = m.group(0)
        return run.translate(_OCR_FIX) if any(c.isdigit() for c in run) else run
    return _NUMERIC_RUN.sub(sub, text)


def repair_separators(text: str) -> str:
    """Re-insert separators a recogniser dropped: 'MFG02/2025', '2022were published'."""
    text = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", text)
    return re.sub(r"(?<=\d)(?=[A-Za-z])", " ", text)


REPAIRS = [("numeral confusions", fix_numerals),
           ("dropped separators", lambda t: repair_separators(fix_numerals(t)))]


def _read_confidently(spec, f, regex):
    """MATCH | (ONLY_AFTER_CORRECTION, how) | NO_MATCH.

    A format check may only accuse on text we are confident we read correctly. If the
    declaration matches once known OCR damage is repaired, the label is probably fine and
    the recogniser was wrong - which is a human's call, not a violation. Repair can only
    downgrade FAIL to INDETERMINATE; it never produces a PASS."""
    if re.search(regex, f.text):
        return "MATCH", None
    for how, fn in REPAIRS:
        if re.search(regex, fn(f.text)):
            return "ONLY_AFTER_CORRECTION", how
    return "NO_MATCH", None


def _r(spec, verdict, reason, **ev) -> Result:
    return Result(check=spec["check"], clause=spec["clause"], verdict=verdict,
                  reason=reason, citation=spec.get("citation", {}), evidence=ev)


# ------------------------------------------------------------------ 1. presence ---
def presence(spec, scan: Scan, fields: dict[str, Field | None]) -> Result:
    f = fields.get(spec["field"])
    if f:
        return _r(spec, Verdict.PASS, f"found on {f.panel} panel",
                  text=f.text, score=f.score, margin=f.margin, panel=f.panel)
    # Absence of evidence is not evidence of absence. Three separate reasons we might
    # not have found a declaration, and only one of them is a violation.
    if not {"FRONT", "BACK"} <= scan.panels_captured:
        missing = sorted({"FRONT", "BACK"} - scan.panels_captured)
        return _r(spec, Verdict.INDETERMINATE,
                  f"not found, but {', '.join(missing)} panel(s) were never photographed",
                  panels_captured=sorted(scan.panels_captured))

    d = getattr(fields, "diag", {}).get(spec["field"], {})
    from .extract import NEAR_MISS, LEGIBLE
    if d.get("top", 0) >= NEAR_MISS:
        return _r(spec, Verdict.INDETERMINATE,
                  "something resembling this declaration is present but could not be "
                  "identified with enough confidence to judge it",
                  best_candidate=d.get("best_text"), score=d.get("top"),
                  margin=d.get("margin"))

    illegible = [t for t in scan.tokens if t.conf < LEGIBLE]
    if illegible:
        return _r(spec, Verdict.INDETERMINATE,
                  f"{len(illegible)} of {len(scan.tokens)} text regions were read below "
                  f"the legibility threshold; absence cannot be concluded from an "
                  f"unreadable image",
                  min_confidence=round(min(t.conf for t in illegible), 2))

    return _r(spec, Verdict.FAIL, "declaration not found on any legibly photographed panel",
              panels_captured=sorted(scan.panels_captured))


# -------------------------------------------------------------- 2. format_regex ---
def format_regex(spec, scan: Scan, fields) -> Result:
    f = fields.get(spec["field"])
    if not f:
        return _r(spec, Verdict.NOT_APPLICABLE, "field not established; presence check governs")
    from .extract import LEGIBLE, ACCUSE
    p = spec["params"]
    verdict, how = _read_confidently(spec, f, p["regex"])
    if verdict == "MATCH":
        if "phrase_any" in p:
            from rapidfuzz import fuzz
            sim = max(fuzz.partial_ratio(w.lower(), f.text.lower()) for w in p["phrase_any"])
            # A phrase-level claim ("thirty characters of required wording are simply
            # not here") survives a few misread glyphs, so it only needs legibility.
            # A character-level claim needs ACCUSE. Different claims, different bars.
            if sim < p["phrase_absent_below"] and \
                    min((t.conf for t in f.tokens), default=1.0) >= LEGIBLE:
                return _r(spec, Verdict.FAIL,
                          f"the prescribed wording is absent (best match {sim:.0f}%)",
                          text=f.text, required_wording=p["phrase_any"])
            if sim < p["phrase_present_at"]:
                return _r(spec, Verdict.INDETERMINATE,
                          f"the prescribed wording is only a {sim:.0f}% match; confirm "
                          f"against the evidence crop before judging",
                          text=f.text, required_wording=p["phrase_any"])
            return _r(spec, Verdict.PASS,
                      f"structure and prescribed wording present ({sim:.0f}% match)",
                      text=f.text)
        return _r(spec, Verdict.PASS, "matches the prescribed form", text=f.text)
    if verdict == "ONLY_AFTER_CORRECTION":
        return _r(spec, Verdict.INDETERMINATE,
                  f"matches the prescribed form once {how} are repaired; the reading, "
                  f"not the label, is in doubt",
                  text=f.text, corrected=fix_numerals(f.text))
    conf = min((t.conf for t in f.tokens), default=1.0)
    if conf < ACCUSE:
        return _r(spec, Verdict.INDETERMINATE,
                  f"does not match the prescribed form, but the region was read at "
                  f"{conf:.2f} confidence - too low to attribute the mismatch to the "
                  f"label rather than the reading",
                  text=f.text, confidence=round(conf, 2),
                  accuse_threshold=ACCUSE)
    return _r(spec, Verdict.FAIL, "does not match the prescribed form",
              text=f.text, expected=spec["params"].get("illustrations"))


# ---------------------------------------------------------- 3. numeric_predicate ---
def numeric_predicate(spec, scan: Scan, fields) -> Result:
    f = fields.get(spec["field"])
    if not f or "amount" not in f.normalized:
        return _r(spec, Verdict.NOT_APPLICABLE, "no numeric value established")
    from .extract import LEGIBLE, ACCUSE
    # Inspect the NUMERAL only. "incl. of all taxes" is full of confusable letters, but
    # they are not part of the value being judged.
    span = re.search(r"(?:rs\.?|₹|inr)\s*([^\s(]+)", f.text, re.I)
    numeral = (span.group(1) if span else f.text).rstrip(").,")
    # The parser must consume the WHOLE numeral. The stress run caught "45.b0" being read
    # as 45.0 - the paise were silently dropped and an unrounded price passed as rounded.
    # A value we only partly read is a value we do not know.
    consumed = re.match(r"[0-9OolISB]+(?:[.,][0-9OolISB]{1,2})?$", numeral)
    if not consumed:
        return _r(spec, Verdict.INDETERMINATE,
                  "the numeral could not be read end to end; a partial reading cannot "
                  "support a finding about its value", text=f.text, numeral=numeral)
    if min((t.conf for t in f.tokens), default=1.0) < LEGIBLE or \
       numeral != numeral.translate(_OCR_FIX):
        return _r(spec, Verdict.INDETERMINATE,
                  "the numeral contains characters a recogniser commonly confuses; "
                  "confirm the printed value before judging rounding",
                  text=f.text, numeral=numeral)
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
            # Only a SINGLE recognised region may be measured. An assembled line spans
            # gaps and sometimes two baselines, so its box height is not a glyph height.
            # Real photographs produced ratios of 0.001 from composites - a nonsense
            # number that was being issued as a violation.
            if len(t.src) > 1 or not t.h:
                continue
            letters = [c for c in t.text if c.isalnum() and c not in excl]
            if not letters:
                continue
            ratio = (t.w / len(t.text)) / t.h        # mean advance width over line height
            if worst is None or ratio < worst[0]:
                worst = (ratio, t.text)
    if worst is None:
        return _r(spec, Verdict.INDETERMINATE,
                  "no single recognised region was measurable")
    ratio, text = worst
    # A mean advance width outside this range is a detection artefact - a rotated region,
    # a merged block, a box that clipped the text - not a typographic violation.
    if not 0.05 <= ratio <= 3.0:
        return _r(spec, Verdict.INDETERMINATE,
                  f"measured ratio {ratio:.3f} is outside the physically plausible range; "
                  f"the text region, not the label, is in doubt",
                  ratio=round(ratio, 3), text=text)
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
    if len(q.src) > 1:
        return _r(spec, Verdict.INDETERMINATE,
                  "the quantity declaration was assembled from several recognised "
                  "regions; clear space cannot be measured from a composite box")
    need_v, need_h = p["above_below_multiple"] * q.h, p["left_right_multiple"] * q.h
    got_v = got_h = float("inf")
    for t in scan.tokens:
        if t is q or t.panel != q.panel:
            continue
        if t.x < q.x + q.w and t.x + t.w > q.x:                     # vertically aligned
            got_v = min(got_v, q.y - (t.y + t.h) if t.y < q.y else t.y - (q.y + q.h))
        if t.y < q.y + q.h and t.y + t.h > q.y:                     # horizontally aligned
            got_h = min(got_h, q.x - (t.x + t.w) if t.x < q.x else t.x - (q.x + q.w))
    if got_v < 0 or got_h < 0:
        # Overlapping detection boxes. Real photographs produced -122 px of "clear space",
        # which is a recogniser artefact and must never read as crowding.
        return _r(spec, Verdict.INDETERMINATE,
                  "recognised text regions overlap; the spacing measurement is not "
                  "trustworthy", above_below_px=round(got_v), left_right_px=round(got_h))
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

    from .engine import in_force
    versions = p.get("versions") or [{"effective_from": "2011-04-01", "effective_to": None,
                                      "keyed_by": p["input"], "rows": p["rows"],
                                      "source_instrument": p.get("source_instrument")}]
    live = [v for v in versions if in_force(v, scan.captured_at)]
    if not live:
        return _r(spec, Verdict.INDETERMINATE,
                  f"no version of this table was in force on {scan.captured_at}")
    ver = live[-1]
    if ver["keyed_by"] != "pdp_area_cm2":
        # Pre-2018 law keyed the threshold to net quantity, not panel area.
        key = scan.net_quantity_g if ver["keyed_by"] == "net_quantity_g" else None
        if key is None:
            return _r(spec, Verdict.INDETERMINATE,
                      f"the table in force on {scan.captured_at} is keyed to "
                      f"{ver['keyed_by']}, which was not supplied")
        band = next(r for r in ver["rows"] if r["upper"] is None or key <= r["upper"])
        required = band["molded_mm"] if scan.is_molded else band["min_mm"]
        measured = max((t.cap_height_px or t.h) for f in fields.values() if f
                       for t in f.tokens if f.kind in ("mrp", "net_quantity")) / scan.px_per_mm
        ok = measured >= required
        return _r(spec, Verdict.PASS if ok else Verdict.FAIL,
                  f"measured {measured:.2f} mm against {required} mm required by the "
                  f"table in force on {scan.captured_at} (keyed to net quantity)",
                  measured_mm=round(measured, 2), required_mm=required,
                  law_version=ver["effective_from"], source=ver.get("source_instrument"))

    band, lo = None, 0.0
    for row in ver["rows"]:
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
