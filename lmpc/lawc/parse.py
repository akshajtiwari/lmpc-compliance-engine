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

def extract_text(p: Path) -> str | None:
    """Return the text, or None if the file cannot be read at all.

    One corrupt or truncated download must not take down a whole rulepack build. A file
    we cannot read is recorded as unreadable and excluded from the chain - never
    half-parsed, because a partially recovered gazette is worse than a missing one.
    """
    if p.suffix.lower() == ".txt":
        return p.read_text(encoding="utf-8", errors="replace")
    out = p.with_suffix(".txt")
    try:
        subprocess.run(["pdftotext", "-layout", str(p), str(out)],
                       check=True, capture_output=True, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    try:
        return out.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def page_count(p: Path) -> int:
    if p.suffix.lower() != ".pdf":
        return 1
    try:
        r = subprocess.run(["pdfinfo", str(p)], capture_output=True, text=True, timeout=60)
        return int(r.stdout.split("Pages:")[1].split()[0])
    except Exception:
        return 0

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
SELF_DATE_RE = re.compile(rf"New\s+Delhi,?\s+the\s+{DATE}", re.I)
TITLE_RE = re.compile(r"may be called the (.{10,140}?Rules,\s*\d{4})", re.S | re.I)
FORCE_RE = re.compile(r"shall come into force[^.]{0,160}", re.I)

def _key(gsr: str | None, date: str | None) -> str | None:
    """Instrument identity: number AND year, never the number alone.

    G.S.R. numbers restart every year. G.S.R. 875(E) exists as the General Rules
    amendment of 9 September 2016 AND as the breath-analyser amendment of 28 November
    2025, and both are cited as predecessors by different instruments. Keying a chain on
    the number alone splices unrelated amendments together - a nine-year error, silently
    applied to a scan.
    """
    if not gsr:
        return None
    y = re.search(r"(\d{4})", date or "")
    return f"{gsr}@{y.group(1)}" if y else f"{gsr}@?"


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
    prev_date = norm_date(m.group("pd")) if prev else None
    sd = SELF_DATE_RE.search(re.sub(r"\s+", " ", text))
    self_date = norm_date(sd.group(1)) if sd else None
    self_gsr = f"G.S.R. {s.group(1)}(E)" if s else None
    return {
        "self_date": self_date,
        "self_key": _key(self_gsr, self_date),
        "prev_key": _key(prev, prev_date),
        "self_gsr":   self_gsr,
        "is_first_amendment_of_parent": bool(m and not prev),
        "parent_kind": ("PRINCIPAL_RULES" if parent and "principal" in parent.lower()
                        else "AMENDMENT_OF_AMENDMENT" if parent else None),
        "title":      re.sub(r"\s+", " ", ti.group(1)).strip() if ti else None,
        "commencement": re.sub(r"\s+", " ", f.group(0)).strip() if f else None,
        "base_gsr":   gnum(m, "bg"),
        "base_date":  norm_date(m.group("bd")) if m else None,
        "prev_gsr":   prev,
        "prev_date":  prev_date,
    }

MONTHS = {m: i for i, m in enumerate(
    "January February March April May June July August September October "
    "November December".split(), 1)}

def sortkey(d):
    s = d.get("self_date") or d.get("prev_date") or ""
    m = re.match(r"(\d+)\s+(\w+)\s+(\d{4})", s)
    return (int(m.group(3)), MONTHS.get(m.group(2), 0), int(m.group(1))) if m else (0, 0, 0)

def verify_chain(docs: list, family: str | None = None) -> dict:
    """Walk `prev` pointers backwards from the newest instrument of ONE rule family.

    Two corrections the live corpus forced:
      * identity is (number, year) - see _key();
      * a corpus holds several INDEPENDENT rule families (Packaged Commodities, General,
        Government Approved Test Centre). Merging their chains makes the walk pick an
        arbitrary root and report gaps that are not gaps.
    """
    pool = [d for d in docs if d["self_key"]]
    if family:
        pool = [d for d in pool if d.get("family") == family]
    have = {d["self_key"]: d for d in pool}
    prevs = {d["prev_key"] for d in pool if d["prev_key"]}
    roots = [k for k in have if k not in prevs]
    start = max((have[k] for k in roots), key=sortkey)["self_key"] if roots else None
    walk, missing, seen, cur = [], [], set(), start
    while cur and cur not in seen:
        seen.add(cur)
        d = have.get(cur)
        if not d:
            missing.append({"key": cur}); break
        walk.append({"gsr": d["self_gsr"], "key": cur, "file": d["file"],
                     "prev": d["prev_gsr"], "prev_key": d["prev_key"],
                     "prev_date": d["prev_date"]})
        nxt = d["prev_key"]
        if nxt and nxt not in have:
            missing.append({"gsr": d["prev_gsr"], "key": nxt, "dated": d["prev_date"],
                            "referenced_by": d["self_gsr"], "file": d["file"]})
            break
        cur = nxt
    head = have.get(start)
    return {"family": family, "newest_on_spine": head["self_gsr"] if head else None,
            "walk": walk, "missing_documents": missing,
            "side_branch": [x["self_gsr"] for x in pool
                            if x.get("parent_kind") == "AMENDMENT_OF_AMENDMENT"],
            "complete": not missing}


def root_family(d: dict, by_gsr: dict) -> str | None:
    """Resolve a document's family TRANSITIVELY.

    An instrument may amend the principal rules directly, or amend an earlier amendment
    of them. G.S.R. 226(E) amends the Packaged Commodities principal rules; the deadline
    extensions amend 226(E). All belong to the same family, and the "last amended" chain
    runs straight through both - so grouping on the declared parent alone splits one
    chain into fragments and reports gaps that are not gaps.
    """
    seen, cur = set(), d.get("base_gsr")
    while cur and cur not in seen:
        seen.add(cur)
        parent = by_gsr.get(cur)
        nxt = parent.get("base_gsr") if parent else None
        if not nxt or nxt == cur:
            return cur
        cur = nxt
    return cur


def families(docs: list) -> dict[str, int]:
    by_gsr = {d["self_gsr"]: d for d in docs if d.get("self_gsr")}
    out: dict[str, int] = {}
    for d in docs:
        d["family"] = root_family(d, by_gsr)
        if d["family"]:
            out[d["family"]] = out.get(d["family"], 0) + 1
    return out


def collisions(docs: list) -> list[dict]:
    """Same G.S.R. number, different years - evidence that number-only identity fails."""
    by_num: dict[str, set] = {}
    for d in docs:
        if d["self_gsr"]:
            by_num.setdefault(d["self_gsr"], set()).add(d["self_key"])
    return [{"gsr": g, "instruments": sorted(k)} for g, k in by_num.items() if len(k) > 1]


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
        pages = page_count(p)
        rec = {"file": p.name, "pages": pages,
               "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16]}
        if raw is None:
            rec.update({"kind": "CORRUPT_UNREADABLE", "self_gsr": None, "self_key": None,
                        "prev_gsr": None, "prev_key": None, "prev_date": None,
                        "self_date": None, "base_gsr": None, "parent_kind": None,
                        "title": None, "commencement": None, "base_date": None,
                        "is_first_amendment_of_parent": False,
                        "ops": [], "table_I": None})
            docs.append(rec)
            continue
        rec["kind"] = classify(raw, pages)
        eng = english_only(raw)
        rec.update(lineage(eng))
        rec["ops"] = parse_ops(eng)
        rec["table_I"] = extract_table_I(eng)
        docs.append(rec)
    fams = families(docs)                       # assigns d["family"] in place
    main = max(fams, key=fams.get) if fams else None
    return {"documents": docs, "chain": verify_chain(docs, main),
            "unreadable": [d["file"] for d in docs if d["kind"] == "CORRUPT_UNREADABLE"],
            "chains_by_family": {f: verify_chain(docs, f) for f in fams},
            "families": fams, "primary_family": main,
            "gsr_number_collisions": collisions(docs)}

if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1])), indent=2, ensure_ascii=False))
