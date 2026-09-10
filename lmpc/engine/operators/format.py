"""Operators 2–4 — format_regex, numeric_predicate, tiered_format."""
from __future__ import annotations
import re
from .. import normalize
from ..extract import LEGIBLE, ACCUSE
from ..model import Verdict, Result, Scan, Field
from ._common import r, read_confidently, fix_numerals, _OCR_FIX


# ------------------------------------------------------------ 2. format_regex ---
def format_regex(spec, scan: Scan, fields) -> Result:
    f = fields.get(spec["field"])
    if not f:
        return r(spec, Verdict.NOT_APPLICABLE, "field not established; presence check governs")
    p = spec["params"]
    verdict, how = read_confidently(spec, f, p["regex"])
    if verdict == "MATCH":
        if "phrase_any" in p:
            from rapidfuzz import fuzz
            sim = max(fuzz.partial_ratio(w.lower(), f.text.lower()) for w in p["phrase_any"])
            # A phrase-level claim ("thirty characters of required wording are simply
            # not here") survives a few misread glyphs, so it only needs legibility.
            # A character-level claim needs ACCUSE. Different claims, different bars.
            if sim < p["phrase_absent_below"] and \
                    min((t.conf for t in f.tokens), default=1.0) >= LEGIBLE:
                return r(spec, Verdict.FAIL,
                         f"the prescribed wording is absent (best match {sim:.0f}%)",
                         text=f.text, required_wording=p["phrase_any"])
            if sim < p["phrase_present_at"]:
                return r(spec, Verdict.INDETERMINATE,
                         f"the prescribed wording is only a {sim:.0f}% match; confirm "
                         f"against the evidence crop before judging",
                         text=f.text, required_wording=p["phrase_any"])
            return r(spec, Verdict.PASS,
                     f"structure and prescribed wording present ({sim:.0f}% match)",
                     text=f.text)
        return r(spec, Verdict.PASS, "matches the prescribed form", text=f.text)
    if verdict == "ONLY_AFTER_CORRECTION":
        return r(spec, Verdict.INDETERMINATE,
                 f"matches the prescribed form once {how} are repaired; the reading, "
                 f"not the label, is in doubt",
                 text=f.text, corrected=fix_numerals(f.text))
    conf = min((t.conf for t in f.tokens), default=1.0)
    if conf < ACCUSE:
        return r(spec, Verdict.INDETERMINATE,
                 f"does not match the prescribed form, but the region was read at "
                 f"{conf:.2f} confidence - too low to attribute the mismatch to the "
                 f"label rather than the reading",
                 text=f.text, confidence=round(conf, 2), accuse_threshold=ACCUSE)
    return r(spec, Verdict.FAIL, "does not match the prescribed form",
             text=f.text, expected=spec["params"].get("illustrations"))


# ---------------------------------------------------------- 3. numeric_predicate ---
def numeric_predicate(spec, scan: Scan, fields) -> Result:
    f = fields.get(spec["field"])
    if not f or "amount" not in f.normalized:
        return r(spec, Verdict.NOT_APPLICABLE, "no numeric value established")
    if any(t.repaired for t in f.tokens):
        # Repair exists to LOCATE a declaration, never to READ its value. Respacing
        # "4S.3s" into "4 S.3 s" let the parser read "4", call it rounded, and pass an
        # unrounded price - a silent miss manufactured by our own correction.
        return r(spec, Verdict.INDETERMINATE,
                 "the value was read from a repaired transcription; confirm the printed "
                 "numeral before judging it", text=f.text)
    # Inspect the NUMERAL only. "incl. of all taxes" is full of confusable letters, but
    # they are not part of the value being judged.
    span = re.search(r"(?:rs\.?|₹|inr)\s*([^\s(]+)", f.text, re.I)
    numeral = (span.group(1) if span else f.text).rstrip(").,")
    # The parser must consume the WHOLE numeral. The stress run caught "45.b0" being read
    # as 45.0 - the paise were silently dropped and an unrounded price passed as rounded.
    # A value we only partly read is a value we do not know.
    consumed = re.match(r"[0-9OolISB]+(?:[.,][0-9OolISB]{1,2})?$", numeral)
    if not consumed:
        return r(spec, Verdict.INDETERMINATE,
                 "the numeral could not be read end to end; a partial reading cannot "
                 "support a finding about its value", text=f.text, numeral=numeral)
    if min((t.conf for t in f.tokens), default=1.0) < LEGIBLE or \
       numeral != numeral.translate(_OCR_FIX):
        return r(spec, Verdict.INDETERMINATE,
                 "the numeral contains characters a recogniser commonly confuses; "
                 "confirm the printed value before judging rounding",
                 text=f.text, numeral=numeral)
    amt = f.normalized["amount"]
    pred = spec["params"]["predicate"]
    ok = getattr(normalize, pred)(amt)
    return r(spec, Verdict.PASS if ok else Verdict.FAIL,
             f"{amt} {'satisfies' if ok else 'violates'} {pred}", amount=amt)


# ------------------------------------------------------------- 4. tiered_format ---
def tiered_format(spec, scan: Scan, fields) -> Result:
    usp, qty = fields.get("unit_sale_price"), fields.get("net_quantity")
    if not usp:
        return r(spec, Verdict.NOT_APPLICABLE, "no unit sale price declared")
    if not qty or "unit" not in qty.normalized:
        return r(spec, Verdict.INDETERMINATE, "net quantity not established; cannot pick the tier")
    v, u = qty.normalized["value"], qty.normalized["unit"]
    want = ("Rs. _ per kg" if u == "g" and v >= 1000 else
            "Rs. _ per g" if u == "g" else
            "Rs. _ per litre" if u == "ml" and v >= 1000 else
            "Rs. _ per ml" if u == "ml" else "Rs. _ per number")
    unit_word = want.rsplit(" ", 1)[-1]
    ok = re.search(rf"per\s+{unit_word}\b", usp.text, re.I)
    return r(spec, Verdict.PASS if ok else Verdict.FAIL,
             f"quantity {v}{u} requires the form '{want}'", declared=usp.text, required=want)