"""
Full validation campaign. One command, one report.

Covers the three areas the architecture is judged on:
  A. taking the data      — live fetch, classification, identity, chain, families
  B. making it comparable — compilation, review cross-check, reproducibility, integrity
  C. the comparison       — verdicts under noise, at boundaries, across time
"""
from __future__ import annotations
import json, subprocess, sys, tempfile
from pathlib import Path

from lmpc.lawc import build as B, parse
from lmpc.engine.engine import run
from lmpc.engine.model import Verdict
from lmpc.labels.generate import make, COMPLIANT_LINES
from stress.run import noise_sweep, sensitivity_sweep, scenario_pass, verdicts

G, R, Y, D, E = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
rows: list[tuple[str, str, bool, str]] = []


def check(area: str, name: str, ok: bool, detail: str = ""):
    rows.append((area, name, ok, detail))
    print(f"  {G + 'PASS' + E if ok else R + 'FAIL' + E}  {name:<52}{D}{detail}{E}")


# ------------------------------------------------------------ A. taking the data ---
def area_ingestion():
    print(f"\n{Y}A. TAKING THE DATA{E}")
    pcr, gen = parse.main(Path("corpus")), parse.main(Path("corpus_general"))

    d = pcr["documents"]
    digital = sum(1 for x in d if x["kind"] == "DIGITAL")
    check("A", "live corpus fetched and classified", len(d) >= 30,
          f"{len(d)} documents, {digital} machine-readable, {len(d)-digital} need OCR")

    check("A", "scanned gazettes excluded, never half-parsed",
          all(x["self_gsr"] is None for x in d if x["kind"] == "SCANNED_NEEDS_OCR"),
          "2011-2015 two-column scans")

    gd = gen["documents"]
    idr = sum(1 for x in gd if x["self_gsr"]) / len(gd)
    check("A", "parser generalises to an unseen rule family", idr >= 0.9,
          f"General Rules + GATC: {idr:.0%} self-identified, never seen in development")

    col = gen["gsr_number_collisions"]
    check("A", "G.S.R. number collisions detected", bool(col),
          f"{col[0]['gsr']} exists in {' and '.join(k.split('@')[1] for k in col[0]['instruments'])}"
          if col else "none found - expected at least one")

    fam = gen["chains_by_family"]
    check("A", "independent rule families walked separately", len(fam) >= 2,
          " · ".join(f"{k} {len(v['walk'])} links" for k, v in fam.items()))

    ch = pcr["chain"]
    check("A", "amendment chain reconstructed to the newest instrument",
          ch["newest_on_spine"] == "G.S.R. 418(E)" and len(ch["walk"]) >= 12,
          f"{ch['newest_on_spine']} (29 May 2026) via {len(ch['walk'])} links")

    check("A", "missing instrument named, not silently skipped",
          any(m.get("gsr") == "G.S.R. 910(E)" for m in ch["missing_documents"]),
          "G.S.R. 910(E) 29 Dec 2022 - absent from the government's own page")

    with tempfile.TemporaryDirectory() as t:
        tp = Path(t)
        (tp / "broken.pdf").write_bytes(b"%PDF-1.4\n" + b"\x00" * 4000)
        (tp / "empty.pdf").write_bytes(b"")
        try:
            out = parse.main(tp)
            ok = len(out["unreadable"]) == 2
        except Exception:
            ok = False
    check("A", "corrupt downloads survive ingestion", ok,
          "recorded unreadable, build continues")


# --------------------------------------------------- B. making it comparable ---
def area_compilation(pack):
    print(f"\n{Y}B. MAKING IT COMPARABLE{E}")
    chk = next(c for c in pack["checks"] if c["check"] == "LMPC-R7-2-MIN-HEIGHT")
    rows_ = chk["params"]["rows"]
    check("B", "Table-I lifted from the gazette matches the reviewer",
          [(r["upper_cm2"], r["min_mm"], r["molded_mm"]) for r in rows_] ==
          [(50, 1.0, 1.5), (100, 1.5, 3.0), (500, 2.5, 4.0), (2500, 4.0, 6.0),
           (None, 6.0, 6.0)], "G.S.R. 629(E) p.11, cross-checked; build fails on drift")

    check("B", "repealed table retained for old inspections",
          any(v["keyed_by"] == "net_quantity_g" for v in chk["params"]["versions"]),
          "pre-2018 net-quantity table kept so old findings stay reproducible")

    check("B", "boundary operators flagged unconfirmed",
          all(not r["boundary_confirmed_by_human"] for r in rows_),
          "text layer drops the '≤' glyph; all 5 rows await a human")

    with tempfile.TemporaryDirectory() as t:
        a = B.build(out=Path(t) / "a")
        b = B.build(out=Path(t) / "b")
        check("B", "same corpus produces the same hash", a["sha256"] == b["sha256"],
              a["sha256"][:16])
        p = Path(t) / "a" / "current.json"
        j = json.loads(p.read_text())
        next(c for c in j["checks"] if c["check"] == "LMPC-R7-2-MIN-HEIGHT")[
            "params"]["rows"][2]["min_mm"] = 0.1
        p.write_text(json.dumps(j))
        try:
            B.load(Path(t) / "a"); tampered = False
        except B.BuildFailed:
            tampered = True
    check("B", "tampered rulepack refused at load", tampered,
          "thresholds cannot be quietly weakened")

    check("B", "every chain gap carries a named reviewer and a disclosure",
          all(g["reviewer"] and g["text"] for g in pack["currency"]["acknowledged_gaps"]),
          f"{len(pack['currency']['acknowledged_gaps'])} disclosed, printed on every report")

    check("B", "every check cites a clause and a gazette page",
          all(c.get("clause") and c.get("citation", {}).get("gsr") for c in pack["checks"]),
          f"{len(pack['checks'])} checks, {len(pack['gates'])} gates")


# ------------------------------------------------------------ C. the comparison ---
def area_comparison(pack):
    print(f"\n{Y}C. THE COMPARISON{E}")
    ok, bad, _ = scenario_pass(pack, quiet=True)
    check("C", "scenario expectations met", bad == 0, f"{ok} of {ok + bad}")

    worst = noise_sweep(pack, quiet=True)
    check("C", "no false accusations under OCR noise", worst <= 0.02,
          f"worst false-FAIL rate {worst:.0%} across 0-40% character error")

    sens = sensitivity_sweep(pack, quiet=True)
    missed = sum(m for *_, m in sens)
    caught = [c / 60 for lv, _, c, _, _ in sens if lv <= 0.1]
    check("C", "no violation silently passes", missed == 0, f"{missed} missed")
    check("C", "violations still caught inside the operating envelope",
          min(caught) >= 0.75, f"{min(caught):.0%}-{max(caught):.0%} caught up to 10% error")

    # all five Table-I bands
    band_ok = True
    for area, row in zip([30, 75, 215, 1200, 4000], next(
            c for c in pack["checks"] if c["check"] == "LMPC-R7-2-MIN-HEIGHT")["params"]["rows"]):
        side = area ** 0.5
        lab = make(lines=COMPLIANT_LINES, pdp_h_cm=side, pdp_w_cm=side,
                   cap_mm=row["min_mm"] + 1.0, net_quantity_g=500)
        r = {x.check: x for x in run(pack, lab.scan)["results"]}["LMPC-R7-2-MIN-HEIGHT"]
        band_ok &= r.verdict is Verdict.PASS and r.evidence["required_mm"] == row["min_mm"]
    check("C", "all five Table-I bands exercised", band_ok, "30, 75, 215, 1200, 4000 cm2")

    edge_ok = True
    for area in (50, 100, 500, 2500):
        side = area ** 0.5
        lab = make(lines=COMPLIANT_LINES, pdp_h_cm=side, pdp_w_cm=side, cap_mm=3.0,
                   net_quantity_g=500)
        edge_ok &= {x.check: x for x in run(pack, lab.scan)["results"]}[
            "LMPC-R7-2-MIN-HEIGHT"].verdict is Verdict.INDETERMINATE
    check("C", "every table boundary abstains", edge_ok,
          "50, 100, 500, 2500 cm2 - '<' vs '≤' unresolved")

    def r7(day, cap):
        lab = make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=cap,
                   net_quantity_g=500)
        lab.scan.captured_at = day
        return {x.check: x for x in run(pack, lab.scan)["results"]}["LMPC-R7-2-MIN-HEIGHT"]

    check("C", "the law in force on the inspection date governs",
          r7("2017-12-31", 2.2).verdict is Verdict.PASS and
          r7("2018-01-01", 2.2).verdict is Verdict.FAIL,
          "2.2 mm on 500 g: lawful on 31 Dec 2017, unlawful on 1 Jan 2018")

    check("C", "a later amendment cannot rewrite an older finding",
          r7("2016-01-01", 2.2).evidence["law_version"] == "2011-04-01",
          "old scans keep the table that governed them")

    lab = make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.8,
               net_quantity_g=500)
    check("C", "every verdict carries clause, reason and citation",
          all(r.citation and r.reason for r in run(pack, lab.scan)["results"]),
          "no unexplained pass or fail reaches a report")


def main() -> int:
    pack = B.load()
    c = pack["currency"]
    print(f"{Y}VALIDATION CAMPAIGN{E}  rulepack {pack['version']} sha {pack['sha256'][:12]}")
    print(f"current to {c['newest_instrument']} · {c['chain_links_verified']} chain links "
          f"· {len(c['acknowledged_gaps'])} disclosed gap(s)")
    area_ingestion()
    area_compilation(pack)
    area_comparison(pack)
    failed = [r for r in rows if not r[2]]
    print(f"\n{'=' * 78}\n{len(rows) - len(failed)} of {len(rows)} checks passed")
    for a, n, _, d in failed:
        print(f"  {R}FAILED{E} [{a}] {n} — {d}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
