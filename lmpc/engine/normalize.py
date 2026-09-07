"""Turn label text into comparable values. Every parser here is total: it returns None
rather than guessing, because a guessed value becomes a legal finding."""
from __future__ import annotations
import re

MONTHS = {m[:3].lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}

# OCR routinely returns O for 0, l/I for 1, S for 5. Only applied inside a numeric span.
DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "B": "8"})


def money(text: str) -> dict | None:
    m = re.search(r"(?:rs\.?|₹|inr)\s*([0-9OolISB]+(?:[.,][0-9OolISB]{1,2})?)", text, re.I)
    if not m:
        return None
    raw = m.group(1).translate(DIGIT_FIX).replace(",", ".")
    try:
        return {"amount": float(raw), "currency": "INR"}
    except ValueError:
        return None


def quantity(text: str) -> dict | None:
    m = re.search(r"([0-9OolISB]+(?:\.[0-9OolISB]+)?)\s*(kgs?|kg|gms?|gm|g|mls?|ml|"
                  r"litres?|liters?|ltr|l|nos?|n|u)\b", text, re.I)
    if not m:
        return None
    try:
        v = float(m.group(1).translate(DIGIT_FIX))
    except ValueError:
        return None
    u = m.group(2).lower().rstrip("s")
    canon = {"kg": ("g", 1000), "gm": ("g", 1), "g": ("g", 1), "ml": ("ml", 1),
             "litre": ("ml", 1000), "liter": ("ml", 1000), "ltr": ("ml", 1000),
             "l": ("ml", 1000), "no": ("n", 1), "n": ("n", 1), "u": ("n", 1)}
    if u not in canon:
        return None
    unit, mul = canon[u]
    return {"value": v * mul, "unit": unit, "as_printed": m.group(0).strip()}


def month_year(text: str) -> dict | None:
    m = re.search(r"\b(0?[1-9]|1[0-2])\s*[/-]\s*(\d{2,4})\b", text)
    if m:
        y = int(m.group(2))
        return {"month": int(m.group(1)), "year": y + 2000 if y < 100 else y}
    m = re.search(r"\b([a-z]{3,9})\.?\s*,?\s*(\d{4})\b", text, re.I)
    if m and m.group(1)[:3].lower() in MONTHS:
        return {"month": MONTHS[m.group(1)[:3].lower()], "year": int(m.group(2))}
    return None


def rounded_to_rupee_or_50_paise(amount: float) -> bool:
    """Rule 6(1)(e) as amended in 2017: price rounded to the nearest rupee or 50 paise."""
    return abs(round(amount * 2) - amount * 2) < 1e-6
