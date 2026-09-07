"""
Step 2 of what replaced the language model: scored candidate selection.

A photo yields many text lines. Which one is *the* MRP? Each line is scored on features a
person can read off the page, the best one wins — but only if it clears an absolute floor
AND beats the runner-up by a margin. A close call is not a guess; it is INDETERMINATE and
an officer decides.

Every weight lives here in the open and is printed in the evidence panel, so "why did you
think that was the MRP?" has a numeric answer.
"""
from __future__ import annotations
import re
from .model import Token, Scan, Field
from . import lexicon, normalize

FLOOR = 45.0        # below this, nothing was really found
MARGIN = 12.0       # two candidates closer than this are indistinguishable

NEGATIVE = re.compile(
    r"\b(ingredients?|nutrition(al)?|allergen|recipe|storage|directions?|"
    r"best\s+before|contents?\s+may|serving)\b", re.I)

TAXES = re.compile(r"incl\.?(?:usive)?\s+of\s+all\s+taxes", re.I)


def _anchor(text: str, kind: str) -> float:
    """Fuzzy heading similarity, scaled. Uses step 1."""
    sim = lexicon.match(text, kind)
    return 40.0 * (sim / 100.0) if sim >= lexicon.THRESHOLD else 12.0 * (sim / 100.0)


def score(tok: Token, kind: str, scan: Scan) -> tuple[float, dict]:
    t = tok.text
    f: dict[str, float] = {"anchor": _anchor(t, kind)}

    if kind == "mrp":
        f["value_pattern"] = 25.0 if normalize.money(t) else 0.0
        f["cotext_taxes"] = 20.0 if TAXES.search(t) else 0.0
    elif kind == "net_quantity":
        q = normalize.quantity(t)
        f["value_pattern"] = 25.0 if q else 0.0
        # A price on the same line means this is the unit-sale-price line, not the quantity.
        f["not_a_price"] = -18.0 if normalize.money(t) else 0.0
    elif kind == "mfg_date":
        f["value_pattern"] = 25.0 if normalize.month_year(t) else 0.0
    elif kind == "consumer_care":
        f["value_pattern"] = 22.0 if re.search(r"(\+?\d[\d\s-]{8,}|\S+@\S+\.\S+)", t) else 0.0
    elif kind == "manufacturer_block":
        f["value_pattern"] = 22.0 if re.search(r"\b\d{6}\b", t) else 0.0   # PIN code
    elif kind == "country_of_origin":
        f["value_pattern"] = 20.0 if re.search(r"(?i)\b(made in|country of origin)\b", t) else 0.0
    elif kind == "unit_sale_price":
        f["value_pattern"] = 25.0 if re.search(r"(?i)per\s+(g|kg|ml|l|litre|cm|m|number)\b", t) else 0.0

    f["on_pdp"] = 8.0 if tok.panel == "FRONT" else 0.0
    f["negative_context"] = -30.0 if NEGATIVE.search(t) else 0.0
    f["low_ocr_confidence"] = -25.0 * (1.0 - tok.conf) if tok.conf < 0.8 else 0.0
    return sum(f.values()), f


def extract(scan: Scan, kinds: list[str]) -> dict[str, Field | None]:
    """Return the winning candidate per field kind, or None when too close to call."""
    out: dict[str, Field | None] = {}
    for kind in kinds:
        ranked = sorted(((score(t, kind, scan), t) for t in scan.tokens),
                        key=lambda p: p[0][0], reverse=True)
        if not ranked:
            out[kind] = None
            continue
        (top, feats), tok = ranked[0]
        second = ranked[1][0][0] if len(ranked) > 1 else 0.0
        margin = top - second
        if top < FLOOR or margin < MARGIN:
            out[kind] = None
            continue
        fl = Field(kind=kind, text=tok.text, tokens=[tok], score=round(top, 1),
                   margin=round(margin, 1))
        fl.normalized = ({"mrp": normalize.money, "net_quantity": normalize.quantity,
                          "mfg_date": normalize.month_year}.get(kind, lambda _: {}) )(tok.text) or {}
        fl.normalized["_features"] = {k: round(v, 1) for k, v in feats.items() if v}
        out[kind] = fl
    return out


def why(scan: Scan, kind: str, n: int = 3) -> list[tuple[float, str]]:
    """Explain a selection — the top n candidates and their scores. Used in reports."""
    ranked = sorted(((score(t, kind, scan)[0], t.text) for t in scan.tokens), reverse=True)
    return [(round(s, 1), t) for s, t in ranked[:n]]
