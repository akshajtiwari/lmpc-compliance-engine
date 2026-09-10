#!/usr/bin/env python3
"""
lawc — a small law compiler for the Legal Metrology (Packaged Commodities) Rules, 2011.

Proves the claim in docs/03-ENGINEERING-PLAN.md: an amendment gazette can be turned into
rulepack changes automatically, so a human approves a diff instead of retyping YAML.

Stages
  L1  classify + extract text (pdftotext), keep the English rendition   [this module]
  L2  parse the closing Note -> lineage, and verify the chain           [chain.py]
  L3  parse amendment prose -> typed patch operations                   [ops.py]
  L4  extract substituted tables -> numeric parameters                  [ops.py]

Usage:  python3 -m lmpc.lawc.parse <dir-of-pdfs-or-txts>
No third-party packages. Requires poppler's `pdftotext` only for PDF input.
"""
import re, sys, json, hashlib, subprocess
from pathlib import Path

from .chain import lineage, verify_chain, families, collisions
from .ops import parse_ops, extract_table_I

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


# ------------------------------------------------------------------- driver ---

_UNREADABLE = {"kind": "CORRUPT_UNREADABLE", "self_gsr": None, "self_key": None,
               "prev_gsr": None, "prev_key": None, "prev_date": None,
               "self_date": None, "base_gsr": None, "parent_kind": None,
               "title": None, "commencement": None, "base_date": None,
               "is_first_amendment_of_parent": False, "ops": [], "table_I": None}


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
            rec.update(_UNREADABLE)
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