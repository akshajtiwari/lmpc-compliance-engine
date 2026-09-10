"""L3 — amendment prose to typed patch operations; L4 — substituted table values."""
import re

# ------------------------------------------------------- L3: patch operations ---
TARGET_RE = re.compile(
    r"(?:in the said rules|of the principal rules|the principal rules)[,\s]*"
    r"(?:in\s+)?rule\s+(\d+)", re.I)

VERBS = [
    ("substitute", r"for\s+(?P<what>.{3,90}?)\s*,?\s*the following.{0,60}?shall be substituted"),
    ("substitute", r"for\s+the\s+(?P<what>Table\s*[-–]?\s*[IVX]+).{0,60}?shall be substituted"),
    ("insert",     r"after\s+(?P<what>.{3,90}?)\s*,?\s*the following.{0,60}?shall be inserted"),
    ("omit",       r"(?P<what>.{3,60}?)\s+shall be omitted"),
    ("renumber",   r"(?P<what>.{3,60}?)\s+shall be (?:numbered|renumbered)"),
    ("substitute_words", r"for the words[, ]+(?P<what>.{3,120}?)\s*,?\s*the (?:words|figures).{0,80}?shall be substituted"),
]
SUBRULE_RE = re.compile(r"sub-rule\s*\((\d+[A-Z]?)\)", re.I)
CLAUSE_RE  = re.compile(r"clause\s*\(([a-z]+)\)", re.I)
TABLE_RE   = re.compile(r"Table\s*[-–]?\s*([IVX]+)", re.I)


def node_id(rule, what):
    """Stable address in the rule tree. Bindings attach here, not to values —
    which is why a table substitution needs no human editing."""
    parts = [f"lmpc/r{rule}"] if rule else ["lmpc/?"]
    if (m := SUBRULE_RE.search(what)): parts.append(f"sr{m.group(1)}")
    if (m := CLAUSE_RE.search(what)):  parts.append(f"cl{m.group(1)}")
    if (m := TABLE_RE.search(what)):   parts.append(f"table-{m.group(1).upper()}")
    return "/".join(parts)


def parse_ops(text: str) -> list:
    t = re.sub(r"[ \t]+", " ", text)
    ops, rule = [], None
    for chunk in re.split(r"(?<=[;.])\s*\n", t):
        if (m := TARGET_RE.search(chunk)):
            rule = m.group(1)
        for op, pat in VERBS:
            for m in re.finditer(pat, chunk, re.I | re.S):
                what = re.sub(r"\s+", " ", m.group("what")).strip(" ,“”\"")
                if len(what) > 90 or not what:
                    continue
                ops.append({"op": op, "rule": rule, "target": what,
                            "node": node_id(rule, what),
                            "quote": re.sub(r"\s+", " ",
                                            chunk[max(0, m.start()-60):m.end()+70]).strip()})
    # de-duplicate on (op, node, target)
    seen, out = set(), []
    for o in ops:
        k = (o["op"], o["node"]) if "table-" in o["node"] else (o["op"], o["node"], o["target"].lower())
        if k not in seen:
            seen.add(k); out.append(o)
    return out


# ----------------------------------------------------------- L4: table values ---
ROW_RE = re.compile(
    r"^\s*(\d)\s+(?P<cond>[0-9]+\s*[<≤>=]+\s*A|A\s*[<≤>=]+\s*[0-9]+|"
    r"[0-9]+\s*[<≤>=]+\s*A\s*[<≤>=]+\s*[0-9]+)\s+(?P<h>\d+\.\d)\s+(?P<m>\d+\.\d)\s*$")


def extract_table_I(text: str) -> dict | None:
    """Lift Table-I rows from the substituted table. Boundary operators are the
    dangerous part: pdftotext renders '≤' as '<' when the glyph is missing from
    the embedded font, so every boundary is flagged for human confirmation."""
    if "Table-I" not in text and "Table -I" not in text and "Table- I" not in text:
        return None
    rows = []
    for line in text.splitlines():
        if (m := ROW_RE.match(line.replace("|", " "))):
            cond = re.sub(r"\s+", " ", m.group("cond"))
            rows.append({
                "band": cond,
                "min_height_mm": float(m.group("h")),
                "min_height_molded_mm": float(m.group("m")),
                "boundary_operators": re.findall(r"[<≤>=]+", cond),
                "needs_human_confirmation": "≤" not in cond,   # glyph may have been lost
            })
    # The table is printed twice (Hindi rendition + English rendition). De-duplicate.
    seen, uniq = set(), []
    for row in rows:
        k = (row["band"], row["min_height_mm"], row["min_height_molded_mm"])
        if k not in seen:
            seen.add(k); uniq.append(row)
    return {"rows": uniq} if uniq else None