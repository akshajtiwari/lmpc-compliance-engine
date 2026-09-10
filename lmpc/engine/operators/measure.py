"""Operators 5–7 — ratio_min, clear_space, table_lookup. The geometry checks."""
from __future__ import annotations
from ..model import Verdict, Result, Scan, Field
from ._common import r


# ---------------------------------------------------------------- 5. ratio_min ---
def ratio_min(spec, scan: Scan, fields) -> Result:
    """Rule 7(3). A pure pixel ratio — no scale reference needed."""
    p = spec["params"]
    excl = set(p.get("exclude_glyphs", []))
    # Rule 7(3) governs "the declaration". Measuring marketing copy is not just useless,
    # it produces violations against text the rule does not cover - a real photograph gave
    # us a FAIL computed from "A QUALITY PRODUCT OF".
    MANDATORY = {"mrp", "net_quantity", "mfg_date", "consumer_care",
                 "manufacturer_block", "country_of_origin", "unit_sale_price"}
    worst = None
    for kind, f in fields.items():
        if not f or kind not in MANDATORY:
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
        return r(spec, Verdict.INDETERMINATE,
                 "no single recognised region was measurable")
    ratio, text = worst
    if not scan.glyph_segmentation:
        # Rule 7(3) compares a LETTER's width to ITS OWN height. What we have is mean
        # advance width over a detection-box height that includes ascenders, descenders
        # and padding - a systematically low ratio. On real photographs this produced 11
        # violations at plausible-looking values like 0.151. Measuring the wrong thing
        # carefully is still measuring the wrong thing.
        return r(spec, Verdict.INDETERMINATE,
                 f"approximate width/height ratio {ratio:.3f} (minimum {p['min']}); "
                 f"Rule 7(3) needs per-letter measurement, which detection boxes do not "
                 f"provide", ratio=round(ratio, 3), minimum=p["min"], text=text,
                 needs="glyph segmentation")
    # A mean advance width outside this range is a detection artefact - a rotated region,
    # a merged block, a box that clipped the text - not a typographic violation.
    if not 0.05 <= ratio <= 3.0:
        return r(spec, Verdict.INDETERMINATE,
                 f"measured ratio {ratio:.3f} is outside the physically plausible range; "
                 f"the text region, not the label, is in doubt",
                 ratio=round(ratio, 3), text=text)
    ok = ratio >= p["min"]
    return r(spec, Verdict.PASS if ok else Verdict.FAIL,
             f"narrowest mean width/height ratio {ratio:.3f} vs minimum {p['min']}",
             ratio=round(ratio, 3), minimum=p["min"], text=text)


# --------------------------------------------------------------- 6. clear_space ---
def clear_space(spec, scan: Scan, fields) -> Result:
    """Rule 8. Also a pure pixel ratio: distance to the nearest other printed matter,
    measured in multiples of the quantity numeral's own height."""
    p = spec["params"]
    f = fields.get(p["field"])
    if not f:
        return r(spec, Verdict.NOT_APPLICABLE, "quantity declaration not established")
    q = f.tokens[0]
    if len(q.src) > 1:
        return r(spec, Verdict.INDETERMINATE,
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
        return r(spec, Verdict.INDETERMINATE,
                 "recognised text regions overlap; the spacing measurement is not "
                 "trustworthy", above_below_px=round(got_v), left_right_px=round(got_h))
    ok = got_v >= need_v and got_h >= need_h
    return r(spec, Verdict.PASS if ok else Verdict.FAIL,
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
        return r(spec, Verdict.INDETERMINATE,
                 "package dimensions not supplied; principal display panel area unknown")
    if scan.px_per_mm is None:
        return r(spec, Verdict.INDETERMINATE,
                 "no scale reference in frame; millimetre height cannot be measured")

    from ..engine import in_force
    versions = p.get("versions") or [{"effective_from": "2011-04-01", "effective_to": None,
                                      "keyed_by": p["input"], "rows": p["rows"],
                                      "source_instrument": p.get("source_instrument")}]
    live = [v for v in versions if in_force(v, scan.captured_at)]
    if not live:
        return r(spec, Verdict.INDETERMINATE,
                 f"no version of this table was in force on {scan.captured_at}")
    ver = live[-1]
    if ver["keyed_by"] != "pdp_area_cm2":
        # Pre-2018 law keyed the threshold to net quantity, not panel area.
        key = scan.net_quantity_g if ver["keyed_by"] == "net_quantity_g" else None
        if key is None:
            return r(spec, Verdict.INDETERMINATE,
                     f"the table in force on {scan.captured_at} is keyed to "
                     f"{ver['keyed_by']}, which was not supplied")
        band = next(rw for rw in ver["rows"] if rw["upper"] is None or key <= rw["upper"])
        required = band["molded_mm"] if scan.is_molded else band["min_mm"]
        measured = max((t.cap_height_px or t.h) for f in fields.values() if f
                       for t in f.tokens if f.kind in ("mrp", "net_quantity")) / scan.px_per_mm
        ok = measured >= required
        return r(spec, Verdict.PASS if ok else Verdict.FAIL,
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
        return r(spec, Verdict.INDETERMINATE,
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
              source=p.get("source_instrument"), law_version=ver["effective_from"])
    if abs(measured - required) <= unc:
        return r(spec, Verdict.INDETERMINATE,
                 f"measured {measured:.2f} +/- {unc:.2f} mm straddles the {required} mm "
                 f"threshold", **ev)
    ok = measured >= required
    return r(spec, Verdict.PASS if ok else Verdict.FAIL,
             f"measured {measured:.2f} mm against a required {required} mm for a "
             f"{area:.0f} cm2 panel", **ev)
