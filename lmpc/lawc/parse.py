#!/usr/bin/env python3
"""
lawc — a small law compiler for the Legal Metrology (Packaged Commodities) Rules, 2011.

Proves the claim in docs/04-ENGINEERING-PLAN.md: an amendment gazette can be turned into
rulepack changes automatically, so a human approves a diff instead of retyping YAML.

Stages
  L1  classify + extract text (pdftotext), keep the English rendition
  L2  parse the closing Note -> lineage, and verify the amendment chain is unbroken
  L3  parse amendment prose -> typed patch operations against rule-tree node IDs
  L4  extract substituted tables -> numeric parameters, flagging unsafe glyph boundaries

Usage:  python3 lawc.py <dir-of-pdfs-or-txts>
No third-party packages. Requires poppler's `pdftotext` only for PDF input.
"""
import re, sys, json, hashlib, subprocess
from pathlib import Path

# ---------------------------------------------------------------- L1: text ---

def extract_text(p: Path) -> str:
    if p.suffix.lower() == ".txt":
        return p.read_text(encoding="utf-8", errors="replace")
    out = p.with_suffix(".txt")
    subprocess.run(["pdftotext", "-layout", str(p), str(out)],
                   check=True, capture_output=True)
    return out.read_text(encoding="utf-8", errors="replace")

DEV = re.compile(r"[ऀ-ॿ]")

def english_only(text: str) -> str:
    """Gazette notifications print Hindi then English. Keep lines that are
    predominantly Latin; a line is dropped if >15% of its letters are Devanagari."""
    keep = []
    for line in text.splitlines():
        letters = [c for c in line if c.isalpha()]
        if not letters:
            keep.append(line); continue
        if len(DEV.findall(line)) / len(letters) <= 0.15:
            keep.append(line)
    return "\n".join(keep)

def classify(text: str, pages: int) -> str:
    return "SCANNED_NEEDS_OCR" if len(text) < 200 * max(pages, 1) else "DIGITAL"

# ------------------------------------------------------------- L2: lineage ---

GSR = r"G\.S\.R[.\s]*(?:number[.\s]*)?\d+\s*\(\s*E\s*\)"
GSR_CAP = r"G\.S\.R[.\s]*(?:number[.\s]*)?(\d+)\s*\(\s*E\s*\)"
DATE = r"(\d{1,2}\s*(?:st|nd|rd|th)?\s+[A-Z][a-z]+,?\s+\d{4})"

# The closing Note names the parent instrument and the immediately preceding amendment.
# Variants seen in the real corpus: "dated the 7th March" vs "dated 27th October";
# "The principal rules were published" vs "The <Title> Rules, 2022 were published"
# (an amendment-of-an-amendment, whose parent is NOT the principal rules).
NOTE_RE = re.compile(
    rf"(?P<parent>principal rules|.{{0,90}}?Rules,\s*\d{{4}}).{{0,40}}?were?\s+published"
    rf".{{0,220}}?(?P<bg>{GSR}).{{0,40}}?dated\s+(?:the\s+)?(?P<bd>{DATE})"
    rf"(?:.{{0,220}}?last\s+amended[,\s]*(?:vide)?[,\s]*(?:notification)?[,\s]*(?:number)?.{{0,60}}?(?P<pg>{GSR}).{{0,40}}?dated\s+(?:the\s+)?(?P<pd>{DATE}))?",
    re.S | re.I)

SELF_RE = re.compile(rf"{GSR_CAP}\s*[.\u2014\u2013:\-]", re.M | re.I)
TITLE_RE = re.compile(r"may be called the (.{10,140}?Rules,\s*\d{4})", re.S | re.I)
FORCE_RE = re.compile(r"shall come into force[^.]{0,160}", re.I)

def gnum(m, key):
    if not m: return None
    return "G.S.R. %s(E)" % re.search(r"(\d+)", m.group(key)).group(1)

def norm_date(d: str) -> str:
    d = re.sub(r"(\d+)\s*(st|nd|rd|th)", r"\1", d)
    return re.sub(r"\s+", " ", d.replace(",", "")).strip()

def lineage(text: str) -> dict:
    t = re.sub(r"\s+", " ", text)
    m = NOTE_RE.search(t)
    s = SELF_RE.search(text)
    ti = TITLE_RE.search(t)
    f = FORCE_RE.search(t)
    parent = re.sub(r"\s+", " ", m.group("parent")).strip() if m else None
    prev = gnum(m, "pg") if m and m.group("pg") else None
    return {
        "self_gsr":   f"G.S.R. {s.group(1)}(E)" if s else None,
        "is_first_amendment_of_parent": bool(m and not prev),
        "parent_kind": ("PRINCIPAL_RULES" if parent and "principal" in parent.lower()
                        else "AMENDMENT_OF_AMENDMENT" if parent else None),
        "title":      re.sub(r"\s+", " ", ti.group(1)).strip() if ti else None,
        "commencement": re.sub(r"\s+", " ", f.group(0)).strip() if f else None,
        "base_gsr":   gnum(m, "bg"),
        "base_date":  norm_date(m.group("bd")) if m else None,
        "prev_gsr":   prev,
        "prev_date":  norm_date(m.group("pd")) if prev else None,
    }

MONTHS = {m: i for i, m in enumerate(
    "January February March April May June July August September October "
    "November December".split(), 1)}

def sortkey(d):
    s = d.get("prev_date") or ""
    m = re.match(r"(\d+)\s+(\w+)\s+(\d{4})", s)
    return (int(m.group(3)), MONTHS.get(m.group(2), 0), int(m.group(1))) if m else (0, 0, 0)

def verify_chain(docs: list) -> dict:
    """Walk `prev` pointers backwards from the newest instrument. A pointer to a
    G.S.R. we do not hold is a MISSING DOCUMENT — an automated completeness proof.
    Only PRINCIPAL_RULES-parented instruments form the consolidation spine;
    amendment-of-amendment instruments hang off it as a side branch."""
    # NOTE: the "last amended" pointer chain and the "which instrument does this
    # amend" declaration are two DIFFERENT graphs. G.S.R. 722(E) amends the principal
    # rules but points back to G.S.R. 714(E), which amends the 2022 Amendment Rules.
    # Filtering the chain by parent_kind breaks the walk. Chain over everything.
    spine = [d for d in docs if d["self_gsr"]]
    branch = [d["self_gsr"] for d in docs if d.get("parent_kind") == "AMENDMENT_OF_AMENDMENT"]
    have = {d["self_gsr"]: d for d in spine}
    prevs = {d["prev_gsr"] for d in spine if d["prev_gsr"]}
    roots = [g for g in have if g not in prevs]
    start = max((have[g] for g in roots), key=sortkey)["self_gsr"] if roots else None
    walk, missing, seen, cur = [], [], set(), start
    while cur and cur not in seen:
        seen.add(cur)
        d = have.get(cur)
        if not d:
            missing.append(cur); break
        walk.append({"gsr": cur, "file": d["file"], "prev": d["prev_gsr"],
                     "prev_date": d["prev_date"]})
        nxt = d["prev_gsr"]
        if nxt and nxt not in have:
            missing.append({"gsr": nxt, "dated": d["prev_date"],
                            "referenced_by": cur, "file": d["file"]})
            break
        cur = nxt
    return {"newest_on_spine": start, "walk": walk,
            "missing_documents": missing, "side_branch": branch,
            "complete": not missing}

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
                what = re.sub(r"\s+", " ", m.group("what")).strip(" ,\"“”")
                if len(what) > 90 or not what:
                    continue
                ops.append({"op": op, "rule": rule, "target": what,
                            "node": node_id(rule, what),
                            "quote": re.sub(r"\s+", " ", chunk[max(0, m.start()-60):m.end()+70]).strip()})
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
    for r in rows:
        k = (r["band"], r["min_height_mm"], r["min_height_molded_mm"])
        if k not in seen:
            seen.add(k); uniq.append(r)
    return {"rows": uniq} if uniq else None

# ------------------------------------------------------------------- driver ---

def main(d: Path):
    docs = []
    files = sorted([p for p in d.iterdir() if p.suffix.lower() == ".pdf"]) or \
            sorted([p for p in d.iterdir() if p.suffix.lower() == ".txt"])
    for p in files:
        raw = extract_text(p)
        pages = int(subprocess.run(["pdfinfo", str(p)], capture_output=True, text=True
                    ).stdout.split("Pages:")[1].split()[0]) if p.suffix.lower() == ".pdf" else 1
        kind = classify(raw, pages)
        eng = english_only(raw)
        rec = {"file": p.name, "pages": pages, "kind": kind,
               "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16]}
        rec.update(lineage(eng))
        rec["ops"] = parse_ops(eng)
        rec["table_I"] = extract_table_I(eng)
        docs.append(rec)
    return {"documents": docs, "chain": verify_chain(docs)}

if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1])), indent=2, ensure_ascii=False))
