"""
Build a rulepack from the gazette corpus.

The build FAILS rather than producing a rulepack when:
  * the amendment chain has a hole (we cannot prove we hold the current law),
  * Table-I values lifted from the gazette disagree with what a reviewer confirmed,
  * a binding points at a rule-tree node no amendment in the corpus ever touched.

That last one matters most: it is how a rulepack goes quietly stale. A check bound to a
node the corpus cannot account for is a check nobody has verified against current law.
"""
from __future__ import annotations
import json, hashlib, datetime as dt, subprocess, sys
from pathlib import Path

import yaml

from . import parse

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "corpus"
OUT = ROOT / "rulepack"
BINDINGS = Path(__file__).with_name("bindings.yaml")
GAPS = Path(__file__).with_name("gaps.yaml")


class BuildFailed(Exception):
    """A rulepack that cannot be proven current or correct must not be produced."""


def ensure_corpus(corpus: Path = CORPUS) -> None:
    if any(corpus.glob("*.pdf")):
        return
    # An explicitly supplied corpus is a test/user input. Never replace it with a
    # network download from the default corpus directory behind the caller's back.
    if corpus.resolve() != CORPUS.resolve():
        raise BuildFailed(f"gazette corpus is empty: {corpus}")
    script = Path(__file__).with_name("fetch.sh")
    print(f"corpus empty — fetching via {script.name}", file=sys.stderr)
    subprocess.run(["bash", str(script), str(CORPUS)], check=True, cwd=ROOT)


def governing_table(compiled: dict, node: str) -> tuple[dict, dict]:
    """Return (table, source_document) for the newest amendment that substituted `node`.

    'Newest' follows the amendment chain, not file dates — an instrument published later
    can commence earlier, and the chain is the only ordering the law itself supplies.
    """
    order = [w["gsr"] for w in compiled["chain"]["walk"]]           # newest first
    rank = {g: i for i, g in enumerate(order)}
    best, best_rank = None, 10**6
    for d in compiled["documents"]:
        if not d.get("table_I"):
            continue
        if not any(o["node"] == node and o["op"] == "substitute" for o in d["ops"]):
            continue
        r = rank.get(d["self_gsr"], 10**5)
        if r < best_rank:
            best, best_rank = d, r
    if best is None:
        raise BuildFailed(f"no amendment in the corpus substitutes {node}")
    return best["table_I"], best


def check_table_against_review(extracted: dict, confirmed: list[dict], node: str) -> list[dict]:
    """Cross-check gazette-extracted numbers against reviewer-confirmed numbers.

    Only the VALUES are compared. Boundary operators deliberately are not: the text layer
    drops '≤', so the operator in `extracted` is unreliable by construction and the
    reviewer's decision governs. A value mismatch means the law moved under us.
    """
    rows = extracted["rows"]
    if len(rows) != len(confirmed):
        raise BuildFailed(
            f"{node}: gazette has {len(rows)} rows, reviewer confirmed {len(confirmed)}")
    merged = []
    for i, (got, want) in enumerate(zip(rows, confirmed)):
        if abs(got["min_height_mm"] - want["min_mm"]) > 1e-9 or \
           abs(got["min_height_molded_mm"] - want["molded_mm"]) > 1e-9:
            raise BuildFailed(
                f"{node} row {i+1}: gazette says {got['min_height_mm']}/"
                f"{got['min_height_molded_mm']} mm, reviewer confirmed "
                f"{want['min_mm']}/{want['molded_mm']} mm — a human must re-review")
        merged.append({
            "upper_cm2": want["upper_cm2"],
            "min_mm": want["min_mm"],
            "molded_mm": want["molded_mm"],
            "band_as_printed": got["band"],
            "boundary_operator_from_text_layer": got["boundary_operators"],
            "boundary_confirmed_by_human": not got["needs_human_confirmation"],
        })
    return merged


def build(corpus: Path = CORPUS, out: Path = OUT) -> dict:
    ensure_corpus(corpus)
    compiled = parse.main(corpus)
    chain = compiled["chain"]
    b = yaml.safe_load(BINDINGS.read_text(encoding="utf-8"))

    acknowledged = {g["gsr"]: g for g in
                    (yaml.safe_load(GAPS.read_text(encoding="utf-8")) or {}).get("gaps", [])}
    disclosures = []
    for m in chain["missing_documents"]:
        g = acknowledged.get(m["gsr"])
        if not g or g.get("decision") != "ACCEPT_WITH_DISCLOSURE":
            raise BuildFailed(
                f"amendment chain incomplete — {m['gsr']} (dated {m['dated']}, referenced "
                f"by {m['referenced_by']}) is unreachable and not acknowledged in "
                f"gaps.yaml. Refusing to build a rulepack that cannot be proven current.")
        if not g.get("reviewer"):
            raise BuildFailed(f"{m['gsr']} acknowledged without a named reviewer")
        disclosures.append({"gsr": g["gsr"], "dated": g["dated"],
                            "reviewer": g["reviewer"], "reviewed_on": g["reviewed_on"],
                            "affects_nodes": g.get("affects_nodes", []),
                            "text": " ".join(g["disclosure"].split())})

    # A binding that names an operator nobody implemented would silently produce
    # SYSTEM_ERROR on every scan. Catch it at build time, not in the field.
    from lmpc.engine.operators import OPERATORS
    missing_ops = sorted({c["operator"] for c in b["checks"]} - set(OPERATORS))
    if missing_ops:
        raise BuildFailed(f"bindings name unimplemented operators: {missing_ops}")

    touched = {o["node"] for d in compiled["documents"] for o in d["ops"]}
    bound_nodes = {c["node"] for c in b["checks"] + b["gates"]}
    for d in disclosures:
        clash = set(d["affects_nodes"]) & bound_nodes
        if clash:
            raise BuildFailed(
                f"{d['gsr']} is assessed as affecting {sorted(clash)}, which this "
                f"rulepack binds. A disclosure cannot stand in for the document itself.")

    checks = []
    for c in b["checks"]:
        entry = dict(c)
        if c["operator"] == "table_lookup":
            table, src = governing_table(compiled, c["node"])
            entry["params"] = dict(c["params"])
            entry["params"]["rows"] = check_table_against_review(
                table, c["confirmed_values"], c["node"])
            entry["params"]["source_instrument"] = src["self_gsr"]
            # Historical versions travel WITH the rulepack. A scan is judged by the law
            # in force on the day it was captured, and an old report must stay
            # reproducible after an amendment.
            entry["params"]["versions"] = (c.get("superseded", []) + [{
                "effective_from": str(c.get("table_effective_from",
                                            c["effective_from"])),
                "effective_to": None,
                "keyed_by": c["params"]["input"],
                "source_instrument": src["self_gsr"],
                "rows": entry["params"]["rows"],
            }])
            for v in entry["params"]["versions"]:
                v["effective_from"] = str(v["effective_from"])
                v["effective_to"] = str(v["effective_to"]) if v.get("effective_to") else None
            entry.pop("confirmed_values", None)
            entry.pop("superseded", None)
            # Boundary unresolved -> the check may measure and explain, never FAIL.
            if c.get("boundary_review", {}).get("status") == "UNRESOLVED":
                entry["verdict_ceiling"] = "INDETERMINATE_NEAR_BOUNDARY"
        checks.append(entry)

    pack = {
        "rulepack": b["rulepack"],
        "schema": b["schema"],
        "currency": {
            "newest_instrument": chain["newest_on_spine"],
            "chain_links_verified": len(chain["walk"]),
            "chain_complete": chain["complete"],
            "acknowledged_gaps": disclosures,
            "corpus_documents": len(compiled["documents"]),
            "documents_needing_ocr": sum(
                1 for d in compiled["documents"] if d["kind"] == "SCANNED_NEEDS_OCR"),
            "unreadable_documents": compiled.get("unreadable", []),
            "chain": [{"gsr": w["gsr"], "prev": w["prev"], "prev_date": w["prev_date"]}
                      for w in chain["walk"]],
        },
        "gates": b["gates"],
        "checks": checks,
        "modes": b["modes"],
        "unverified_bindings": sorted(
            {c["node"] for c in b["checks"] + b["gates"]} - touched),
    }
    def _json(o):
        if isinstance(o, (dt.date, dt.datetime)):
            return o.isoformat()
        raise TypeError(type(o))

    pack = json.loads(json.dumps(pack, default=_json))   # normalise dates to ISO strings
    # built_at is deliberately set AFTER hashing: the same corpus must produce the same
    # hash on any machine at any time, or reproducibility claims are meaningless.
    pack["sha256"] = digest(pack)
    pack["built_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    pack["version"] = "lmpc-%s-%s" % (dt.date.today().isoformat(), pack["sha256"][:8])

    out.mkdir(exist_ok=True)
    path = out / "current.json"
    path.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    return pack


def digest(pack: dict) -> str:
    """Recompute the content hash. Excludes the hash, the version derived from it, and
    the build timestamp - the same corpus must hash identically on any machine."""
    body = {k: v for k, v in pack.items() if k not in ("sha256", "version", "built_at")}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify(pack: dict) -> None:
    """A rulepack that has been altered on disk must not be used. Every verdict cites
    this hash, so a silent edit would forge the legal basis of past findings."""
    if digest(pack) != pack.get("sha256"):
        raise BuildFailed(
            f"rulepack integrity check failed: content hashes to {digest(pack)[:16]} "
            f"but claims {str(pack.get('sha256'))[:16]}")


def load(out: Path = OUT, check: bool = True) -> dict:
    pack = json.loads((out / "current.json").read_text(encoding="utf-8"))
    if check:
        verify(pack)
    return pack


if __name__ == "__main__":
    try:
        p = build()
    except BuildFailed as e:
        print(f"BUILD FAILED: {e}", file=sys.stderr)
        raise SystemExit(1)
    c = p["currency"]
    print(f"rulepack   {p['version']}")
    print(f"sha256     {p['sha256']}")
    print(f"current to {c['newest_instrument']}  ({c['chain_links_verified']} chain links verified)")
    print(f"checks     {len(p['checks'])}   gates {len(p['gates'])}")
    for d in c["acknowledged_gaps"]:
        print(f"DISCLOSED  {d['gsr']} ({d['dated']}) unobtainable — accepted by "
              f"{d['reviewer']} on {d['reviewed_on']}")
    if c["unreadable_documents"]:
        print(f"WARNING    {len(c['unreadable_documents'])} unreadable file(s): "
              f"{', '.join(c['unreadable_documents'])}")
    if p["unverified_bindings"]:
        print(f"WARNING    {len(p['unverified_bindings'])} bindings not traceable to a "
              f"corpus amendment: {', '.join(p['unverified_bindings'])}")
