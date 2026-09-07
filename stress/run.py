"""End-to-end stress run: rulepack -> label images -> simulated OCR -> engine -> verdicts."""
from __future__ import annotations
import sys
from lmpc.lawc.build import load
from lmpc.engine.engine import run
from lmpc.labels.generate import make, COMPLIANT_LINES
from stress.scenarios import build

GREEN, RED, DIM, END = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def verdicts(res) -> dict:
    return {r.check: r.verdict.value for r in res["results"]}


def scenario_pass(pack) -> tuple[int, int, list]:
    ok = bad = 0
    failures = []
    print(f"{'scenario':<36}{'check':<30}{'want':<16}{'got'}")
    print("-" * 96)
    for s in build():
        scan = s["label"].scan
        if "mutate" in s:
            s["mutate"](scan)
        got = verdicts(run(pack, scan))
        for check, want in s["expect"].items():
            g = got.get(check, "MISSING")
            good = g == want
            ok, bad = ok + good, bad + (not good)
            col = GREEN if good else RED
            print(f"{s['name']:<36}{check:<30}{want:<16}{col}{g}{END}")
            if not good:
                failures.append((s["name"], check, want, g, s["note"]))
        print(f"{DIM}{'':<36}{s['note']}{END}")
    return ok, bad, failures


def noise_sweep(pack, levels=(0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4), trials=60):
    """The number that matters: how often does a COMPLIANT label get accused as OCR
    degrades? A wrong FAIL is a false accusation; INDETERMINATE is an honest one.

    'clean pass' never reaches 100%: LMPC-R6-1-B-GENERIC-NAME carries an absolute verdict
    ceiling and always returns INDETERMINATE, by design."""
    print(f"\n{'noise':<9}{'trials':<9}{'false FAIL':<13}{'indeterminate':<16}{'clean pass'}")
    print("-" * 62)
    worst = 0.0
    for lv in levels:
        false_fail = indet = clean = 0
        for i in range(trials):
            lab = make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.8,
                       noise=lv, seed=i, net_quantity_g=500)
            r = run(pack, lab.scan)
            c = r["counts"]
            false_fail += c["FAIL"] > 0
            indet += c["FAIL"] == 0 and c["INDETERMINATE"] > 0
            clean += c["FAIL"] == 0 and c["INDETERMINATE"] == 0
        rate = false_fail / trials
        worst = max(worst, rate)
        col = GREEN if rate <= 0.02 else RED
        print(f"{lv:<9.2f}{trials:<9}{col}{rate:>6.0%}{END}{'':<6}"
              f"{indet/trials:>10.0%}{'':<6}{clean/trials:>10.0%}")
    return worst


VIOLATIONS = [
    # (name, lines-mutation, the check that must still catch it)
    ("mrp_wording_absent", {"mrp": "MRP Rs. 45.00"}, "LMPC-R6-1-E-MRP-FORM"),
    ("mrp_not_rounded", {"mrp": "MRP Rs. 45.30 (incl. of all taxes)"},
     "LMPC-R6-1-E-MRP-ROUNDING"),
]


def sensitivity_sweep(pack, levels=(0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3), trials=60):
    """The counter-metric. Withholding accusations is only useful if genuine violations
    are still caught. A system that abstains on everything has a perfect false-accusation
    rate and no value."""
    from stress.scenarios import _lines
    print(f"\n{'noise':<9}{'violation':<26}{'still caught':<15}{'abstained':<12}{'missed'}")
    print("-" * 72)
    rows = []
    for lv in levels:
        for name, repl, check in VIOLATIONS:
            caught = abstained = missed = 0
            for i in range(trials):
                lab = make(lines=_lines(**repl), pdp_h_cm=18.2, pdp_w_cm=11.8,
                           cap_mm=2.8, noise=lv, seed=i, net_quantity_g=500)
                v = verdicts(run(pack, lab.scan)).get(check)
                caught += v == "FAIL"
                abstained += v in ("INDETERMINATE", "NOT_APPLICABLE")
                missed += v == "PASS"
            rate = caught / trials
            col = GREEN if missed == 0 else RED
            print(f"{lv:<9.2f}{name:<26}{col}{rate:>6.0%}{END}{'':<8}"
                  f"{abstained/trials:>7.0%}{'':<5}{missed/trials:>7.0%}")
            rows.append((lv, name, caught, abstained, missed))
    return rows


def main() -> int:
    pack = load()
    c = pack["currency"]
    print(f"rulepack {pack['version']}  sha {pack['sha256'][:12]}")
    print(f"current to {c['newest_instrument']} via {c['chain_links_verified']} verified "
          f"chain links; {len(c['acknowledged_gaps'])} disclosed gap(s)\n")

    ok, bad, failures = scenario_pass(pack)
    worst = noise_sweep(pack)
    sens = sensitivity_sweep(pack)
    missed_total = sum(m for *_, m in sens)

    print(f"\nscenario expectations: {ok} met, {bad} unmet")
    print(f"worst false-FAIL rate on compliant labels: {worst:.0%} (bar: <=2%)")
    print(f"violations silently passed as compliant: {missed_total} (bar: 0)")
    for name, check, want, got, note in failures:
        print(f"  UNMET  {name}: {check} wanted {want}, got {got}  ({note})")
    return 0 if (bad == 0 and worst <= 0.02 and missed_total == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
