"""
Step 1 of what replaced the language model: fuzzy heading matching.

OCR mangles headings — `MR.P`, `M R P`, `MRR`, `एम.आर.पी`. We compare against a curated
synonym list with normalised edit distance and accept above a threshold. Deterministic,
inspectable, and it cannot invent a heading that was never printed.
"""
from __future__ import annotations
import re
from rapidfuzz import fuzz

LEXICON: dict[str, list[str]] = {
    "mrp": ["MRP", "M.R.P", "M.R.P.", "MAX RETAIL PRICE", "MAXIMUM RETAIL PRICE",
            "MAX. RETAIL PRICE", "RETAIL PRICE", "एम.आर.पी", "अधिकतम खुदरा मूल्य"],
    "net_quantity": ["NET QTY", "NET QUANTITY", "NET WT", "NET WEIGHT", "NET VOL",
                     "NET VOLUME", "QTY", "शुद्ध मात्रा", "शुद्ध वजन"],
    "mfg_date": ["MFG", "MFD", "MFG DATE", "DATE OF MANUFACTURE", "PKD", "PACKED ON",
                 "MONTH AND YEAR OF MANUFACTURE", "निर्माण तिथि"],
    "consumer_care": ["CONSUMER CARE", "CUSTOMER CARE", "CONSUMER COMPLAINTS",
                      "GRIEVANCE", "FOR COMPLAINTS", "उपभोक्ता सेवा"],
    "manufacturer_block": ["MANUFACTURED BY", "MFD BY", "PACKED BY", "MARKETED BY",
                           "IMPORTED BY", "निर्मित"],
    "country_of_origin": ["COUNTRY OF ORIGIN", "MADE IN", "उत्पत्ति का देश"],
    "generic_name": ["GENERIC NAME", "COMMON NAME", "PRODUCT"],
    "unit_sale_price": ["UNIT SALE PRICE", "PRICE PER", "UNIT PRICE"],
}

THRESHOLD = 85.0          # normalised similarity, 0–100


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9ऀ-ॿ]", "", s.upper())


def match(text: str, kind: str) -> float:
    """Best similarity of any known spelling of `kind` to a window inside `text`, 0-100.

    partial_ratio, not ratio: the heading is embedded in a longer line
    ("Net Qty: 500 g"), so we are asking whether the line CONTAINS a recognisable
    spelling, not whether the whole line equals one.
    """
    t = _norm(text)
    if not t:
        return 0.0
    best = 0.0
    for syn in LEXICON[kind]:
        n = _norm(syn)
        if len(n) < 3:
            continue
        # A short needle can match noise inside a long line; require the window to be
        # roughly the needle's length by comparing against partial_ratio only.
        best = max(best, fuzz.partial_ratio(n, t))
    return best


def best_kind(text: str) -> tuple[str | None, float]:
    scored = sorted(((match(text, k), k) for k in LEXICON), reverse=True)
    top, kind = scored[0]
    return (kind, top) if top >= THRESHOLD else (None, top)
