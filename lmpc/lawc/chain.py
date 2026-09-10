"""L2 — lineage. Parse the closing Note of each instrument, verify the amendment chain
is unbroken, and group the corpus into independent rule families."""
import re

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

SELF_RE = re.compile(rf"{GSR_CAP}\s*[.—–:\-]", re.M | re.I)
SELF_DATE_RE = re.compile(rf"New\s+Delhi,?\s+the\s+{DATE}", re.I)
TITLE_RE = re.compile(r"may be called the (.{10,140}?Rules,\s*\d{4})", re.S | re.I)
FORCE_RE = re.compile(r"shall come into force[^.]{0,160}", re.I)

MONTHS = {m: i for i, m in enumerate(
    "January February March April May June July August September October "
    "November December".split(), 1)}


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